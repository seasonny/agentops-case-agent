import unittest

from core.diag_bundle import (
    build_bundle_content,
    resolve_bundle_filename,
    should_bundle_outputs,
)
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker


class DiagBundleTests(unittest.TestCase):
    def test_default_mode_does_not_bundle(self):
        config = {"diagnostics": {"bundle_output": {"mode": "off"}}}
        actions = [
            MCPAction(tool="exec_argv", arguments={"argv": ["dig", "x"]}, label="dig"),
        ] * 3
        self.assertFalse(
            should_bundle_outputs(
                config=config,
                actions=actions,
                execution_results=["x" * 5000],
                blocked_commands=[],
            )
        )

    def test_overflow_only_bundles_when_too_long(self):
        config = {
            "diagnostics": {"bundle_output": {"mode": "overflow_only", "overflow_chars": 100}},
        }
        actions = [MCPAction(tool="exec_argv", arguments={"argv": ["dig", "x"]}, label="dig")]
        short = ["ok"]
        long = ["x" * 200]
        self.assertFalse(
            should_bundle_outputs(
                config=config, actions=actions, execution_results=short, blocked_commands=[]
            )
        )
        self.assertTrue(
            should_bundle_outputs(
                config=config, actions=actions, execution_results=long, blocked_commands=[]
            )
        )

    def test_auto_filename_is_not_debug_txt(self):
        name = resolve_bundle_filename({"filename": "auto"}, case_id="01234567")
        self.assertTrue(name.startswith("diag-"))
        self.assertTrue(name.endswith(".txt"))
        self.assertNotEqual(name, "debug.txt")

    def test_build_bundle_includes_blocked_commands(self):
        policy = MCPPolicyChecker()
        content = build_bundle_content(
            case_id="1",
            actions=[MCPAction(tool="exec_argv", arguments={"argv": ["dig", "x"]}, label="dig")],
            execution_results=["out"],
            blocked_commands=["reboot"],
            policy=policy,
        )
        self.assertIn("reboot", content)
        self.assertIn("out", content)


if __name__ == "__main__":
    unittest.main()
