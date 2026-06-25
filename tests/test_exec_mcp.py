import unittest

from core.exec_tool_adapter import (
    EXEC_LOGICAL_TOOL,
    adapt_exec_tool_call,
    format_shell_execute_text,
    try_parse_shell_execute_json,
)
from core.mcp_policy import MCPPolicyChecker
from core.mcp_action import MCPAction, extract_mcp_tool_text
from core.shell_diagnostics import infer_exec_argv_action, infer_shell_diag_actions


class ExecToolAdapterTests(unittest.TestCase):
    def test_adapt_exec_argv_to_shell_execute(self):
        actual, args = adapt_exec_tool_call(
            EXEC_LOGICAL_TOOL,
            {"argv": ["dig", "example.com"], "timeout_seconds": 15, "cwd": "/tmp"},
            {"exec_argv": "shell_execute"},
        )
        self.assertEqual(actual, "shell_execute")
        self.assertEqual(args["command"], ["dig", "example.com"])
        self.assertEqual(args["timeout"], 15)
        self.assertEqual(args["directory"], "/tmp")

    def test_parse_shell_execute_json(self):
        raw = '{"stdout":"ok","stderr":"","status":0}'
        text = try_parse_shell_execute_json(raw)
        self.assertIn("exit_code: 0", text)
        self.assertIn("--- stdout ---", text)
        self.assertIn("ok", text)

    def test_extract_mcp_tool_text_parses_shell_json(self):
        result = {
            "content": [
                {"type": "text", "text": format_shell_execute_text({"stdout": "hi", "stderr": "", "status": 0})}
            ]
        }
        # format_shell_execute_text is plain text; extract should pass through
        text = extract_mcp_tool_text(result)
        self.assertIn("hi", text)


class ShellDiagnosticsTests(unittest.TestCase):
    def test_infer_exec_argv_action(self):
        action = infer_exec_argv_action("dig google.com.tw")
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.tool, "exec_argv")
        self.assertEqual(action.arguments["argv"], ["dig", "google.com.tw"])

    def test_infer_shell_diag_prefers_pods_when_configured(self):
        config = {
            "diagnostics": {
                "pods_exec": {"namespace": "openshift-console", "pod": "console-abc"}
            }
        }
        actions = infer_shell_diag_actions(["dig example.com"], config, allow_host_exec=True)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].tool, "pods_exec")

    def test_infer_shell_diag_falls_back_to_host_exec(self):
        config = {"diagnostics": {"pods_exec": {"namespace": "", "pod": ""}}}
        actions = infer_shell_diag_actions(["ping 8.8.8.8"], config, allow_host_exec=True)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].tool, "exec_argv")


class HostExecPolicyTests(unittest.TestCase):
    def test_blocks_disallowed_binary(self):
        policy = MCPPolicyChecker()
        action = MCPAction(tool="exec_argv", arguments={"argv": ["bash", "-c", "id"]})
        passed, reason = policy.check_action(action)
        self.assertFalse(passed)
        self.assertIn("bash", reason)

    def test_allows_dig(self):
        policy = MCPPolicyChecker()
        action = MCPAction(tool="exec_argv", arguments={"argv": ["dig", "example.com"]})
        passed, _ = policy.check_action(action)
        self.assertTrue(passed)


if __name__ == "__main__":
    unittest.main()
