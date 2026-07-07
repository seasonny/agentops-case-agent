import unittest

from core.agent_settings import init_agent_settings
from core.comment_analyzer import CommentAnalysis
from core.comments import commands_hash
from core.mcp_action import MCPAction
from workflow.runner import (
    RETRIABLE_SKIP_REASONS,
    extract_blocker_signature,
    should_skip_looping_request,
)


class TestExtractBlockerSignature(unittest.TestCase):
    def test_empty_when_no_markers(self):
        self.assertEqual(extract_blocker_signature(["ok", "nodes ready"]), "")

    def test_hashes_sticky_markers(self):
        sig_a = extract_blocker_signature(["Error: no such host: api.example"])
        sig_b = extract_blocker_signature(["no such host in dns lookup"])
        self.assertTrue(sig_a)
        self.assertEqual(sig_a, sig_b)


class TestShouldSkipLoopingRequest(unittest.TestCase):
    def setUp(self):
        init_agent_settings({"agent": {"loop_guard_seconds": 1800}})

    def _analysis(self, commands):
        return CommentAnalysis(
            actionable=True,
            action_type="call_mcp",
            mcp_calls=[MCPAction(tool="exec_argv", arguments={"argv": commands}, label=commands[0])],
        )

    def test_skips_when_same_command_and_blocker_within_guard(self):
        commands = ["dig example.com"]
        memory = {
            "last_command_hash": commands_hash(commands),
            "last_blocker_signature": "abc",
            "last_agent_reply_at": "2099-01-01T00:00:00+00:00",
        }
        self.assertTrue(should_skip_looping_request(memory, self._analysis(commands)))

    def test_does_not_skip_when_blocker_cleared(self):
        commands = ["dig example.com"]
        memory = {
            "last_command_hash": commands_hash(commands),
            "last_blocker_signature": "",
            "last_agent_reply_at": "2099-01-01T00:00:00+00:00",
        }
        self.assertFalse(should_skip_looping_request(memory, self._analysis(commands)))

    def test_does_not_skip_for_non_mcp_action(self):
        memory = {"last_command_hash": "x", "last_blocker_signature": "y"}
        analysis = CommentAnalysis(action_type="clarify")
        self.assertFalse(should_skip_looping_request(memory, analysis))


class TestRetriableSkipReasons(unittest.TestCase):
    def test_llm_unavailable_is_retriable(self):
        self.assertIn("llm_unavailable", RETRIABLE_SKIP_REASONS)
