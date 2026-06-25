import unittest
from unittest import mock

import os

from core.agent_settings import get_loop_guard_seconds, get_reply_prefix, init_agent_settings
from core.comment_analyzer import CommentAnalyzer
from core.config import load_config
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.participants import ParticipantResolver
from core.reply_guardrail import ReplyGuardrail
from core.trigger import TriggerConfig, find_latest_unanswered_trigger_comment
from tests.safe_test_data import SAFE_SUPPORT_AUTHOR


class TestAgentSettings(unittest.TestCase):
    def test_init_from_config(self):
        init_agent_settings(
            {
                "agent": {"reply_prefix": "[TEST] ", "loop_guard_seconds": 99},
                "case": {"comment_public": False},
            }
        )
        self.assertEqual(get_reply_prefix(), "[TEST] ")
        self.assertEqual(get_loop_guard_seconds(), 99)


class TestDangerousPrecheck(unittest.TestCase):
    def test_blocks_before_llm(self):
        config = load_config()
        init_agent_settings(config)
        analyzer = CommentAnalyzer(config, policy_checker=MCPPolicyChecker())
        result = analyzer.analyze("please run reboot on the node")
        self.assertEqual(result.action_type, "dangerous_command")
        self.assertEqual(result.source, "policy")
        self.assertTrue(result.is_processable())


class TestMCPPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = MCPPolicyChecker()

    def test_pods_exec_allowlist(self):
        ok, _ = self.policy.check_action(
            MCPAction(
                tool="pods_exec",
                arguments={
                    "namespace": "x",
                    "name": "y",
                    "command": ["ping", "example.com"],
                },
            )
        )
        self.assertTrue(ok)

    def test_pods_exec_blocks_rm(self):
        ok, reason = self.policy.check_action(
            MCPAction(
                tool="pods_exec",
                arguments={"namespace": "x", "name": "y", "command": ["rm", "-rf", "/"]},
            )
        )
        self.assertFalse(ok)

    def test_upload_path_restricted_when_configured(self):
        policy = MCPPolicyChecker()
        policy.upload_allowed_prefixes = ["/tmp/"]
        ok, _ = policy.check_action(
            MCPAction(
                tool="upload_attachment_rh_portal",
                arguments={"file": "/tmp/must-gather.tar"},
            )
        )
        self.assertTrue(ok)
        bad, _ = policy.check_action(
            MCPAction(
                tool="upload_attachment_rh_portal",
                arguments={"file": "/etc/passwd"},
            )
        )
        self.assertFalse(bad)


class TestTrigger(unittest.TestCase):
    def setUp(self):
        config = load_config()
        init_agent_settings(config)
        self.resolver = ParticipantResolver(config)
        self.demo = TriggerConfig(config)
        self.prod = TriggerConfig(
            {**config, "trigger": {"mode": "production", "ignore_customer_comments": True}}
        )

    def _comment(self, cid, author, content, ts):
        c = {"id": cid, "author": author, "content": content, "timestamp": ts}
        self.resolver.enrich_comments([c])
        return c

    def test_production_skips_customer_finds_support(self):
        comments = [
            self._comment(1, "me", "內部討論", "2026-06-24T10:02:00Z"),
            self._comment(2, SAFE_SUPPORT_AUTHOR, "請執行 oc get node", "2026-06-24T10:01:00Z"),
        ]
        found = find_latest_unanswered_trigger_comment(
            comments, set(), self.resolver, self.prod
        )
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], 2)

    def test_demo_prefix_marks_support(self):
        with mock.patch.dict(os.environ, {"AGENT_DEV_MODE": "1"}):
            config = load_config()
            config["participants"]["demo_trigger_prefix"] = "[SE] "
            resolver = ParticipantResolver(config)
            c = {"id": 1, "author": "me", "content": "[SE] 請確認節點", "timestamp": "2026-06-24T10:00:00Z"}
            resolver.enrich_comments([c])
            self.assertEqual(c["resolved_role"], "support")


class TestReplyGuardrail(unittest.TestCase):
    def setUp(self):
        config = load_config()
        init_agent_settings(config)
        self.guard = ReplyGuardrail(config, policy_checker=MCPPolicyChecker())

    def test_blocks_api_key(self):
        passed, reason, _ = self.guard.validate("token sk-" + "a" * 30)
        self.assertFalse(passed)
        self.assertEqual(reason, "sensitive_content_detected")

    def test_allows_dangerous_mention_when_execution_failed(self):
        from workflow.graph import _allow_dangerous_mention_in_reply

        state = {
            "action_type": "call_mcp",
            "execution_results": [
                'failed to list namespaces: dial tcp: lookup api.example.com: no such host'
            ],
        }
        self.assertTrue(_allow_dangerous_mention_in_reply(state))
        passed, _, _ = self.guard.validate(
            "無法連線叢集，請勿自行 reboot 節點。",
            allow_dangerous_mention=True,
        )
        self.assertTrue(passed)

    def test_allows_dangerous_mention_when_explaining_block(self):
        passed, _, _ = self.guard.validate(
            "無法執行 reboot",
            allow_dangerous_mention=True,
        )
        self.assertTrue(passed)


if __name__ == "__main__":
    unittest.main()
