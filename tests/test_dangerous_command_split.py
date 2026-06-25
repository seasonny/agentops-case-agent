import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.comment_analyzer import CommentAnalyzer
from core.config import load_config
from core.dangerous_command_split import extract_request_lines, split_comment_requests
from core.mcp_policy import MCPPolicyChecker
from core.policy_compiler import compile_policy


MIXED_COMMENT = """請執行

reboot
oc get pod -A
oc get nodes"""


class DangerousCommandSplitTests(unittest.TestCase):
    def test_extract_request_lines_from_mixed_comment(self):
        lines = extract_request_lines(MIXED_COMMENT)
        self.assertEqual(
            lines,
            ["reboot", "oc get pod -A", "oc get nodes"],
        )

    def test_skip_and_continue_splits_safe_lines(self):
        policy = MCPPolicyChecker()

        def is_dangerous(text: str):
            return policy.is_dangerous_command(text)

        split = split_comment_requests(
            MIXED_COMMENT,
            is_dangerous,
            dangerous_handling="skip_and_continue",
        )
        self.assertFalse(split.reject_entire)
        self.assertEqual(split.blocked_lines, ["reboot"])
        self.assertEqual(split.safe_lines, ["oc get pod -A", "oc get nodes"])
        self.assertIn("oc get pod -A", split.safe_text)
        self.assertNotIn("reboot", split.safe_text)

    def test_reject_all_blocks_entire_comment(self):
        policy = MCPPolicyChecker()

        def is_dangerous(text: str):
            return policy.is_dangerous_command(text)

        split = split_comment_requests(
            MIXED_COMMENT,
            is_dangerous,
            dangerous_handling="reject_all",
        )
        self.assertTrue(split.reject_entire)
        self.assertIn("reboot", split.blocked_lines)


class MixedDangerousAnalyzerTests(unittest.TestCase):
    @mock.patch("core.comment_analyzer.is_llm_available", return_value=True)
    @mock.patch("core.comment_analyzer.chat_json")
    def test_skip_and_continue_allows_safe_mcp_calls(self, mock_chat_json, _mock_llm):
        mock_chat_json.return_value = {
            "actionable": True,
            "action_type": "call_mcp",
            "mcp_calls": [
                {
                    "tool": "pods_list",
                    "arguments": {"namespace": ""},
                    "label": "oc get pod -A",
                },
                {
                    "tool": "resources_list",
                    "arguments": {"apiVersion": "v1", "kind": "Node"},
                    "label": "oc get nodes",
                },
            ],
            "intent": "diagnostic",
            "requires_execution": True,
            "summary": "List pods and nodes",
        }
        config = load_config()
        analyzer = CommentAnalyzer(config, policy_checker=MCPPolicyChecker())
        result = analyzer.analyze(MIXED_COMMENT)
        self.assertEqual(result.action_type, "call_mcp")
        self.assertEqual(result.blocked_commands, ["reboot"])
        self.assertEqual(len(result.mcp_calls), 2)
        self.assertNotIn("reboot", str(result.mcp_calls))

    @mock.patch("core.comment_analyzer.is_llm_available", return_value=True)
    @mock.patch("core.comment_analyzer.chat_json")
    def test_reject_all_still_blocks_entire_comment(self, mock_chat_json, _mock_llm):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / "profiles"
            profiles.mkdir()
            for name in ("diagnostic", "enterprise", "minimal"):
                src = Path(__file__).resolve().parents[1] / f"config/policy_profiles/{name}.yaml"
                (profiles / f"{name}.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            policy = root / "policy.yaml"
            policy.write_text(
                "profile: diagnostic\ndangerous_handling: reject_all\n",
                encoding="utf-8",
            )
            cap_map = Path(__file__).resolve().parents[1] / "config/policy_capability_map.yaml"
            compiled = compile_policy(
                policy_path=policy,
                capability_map_path=cap_map,
                profiles_dir=profiles,
            )
            checker = MCPPolicyChecker(compiled=compiled)
        config = load_config()
        analyzer = CommentAnalyzer(config, policy_checker=checker)
        result = analyzer.analyze(MIXED_COMMENT)
        self.assertEqual(result.action_type, "dangerous_command")
        self.assertIn("reboot", result.blocked_commands)
        mock_chat_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
