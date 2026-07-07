import unittest
from unittest import mock

from core.config import load_config
from core.decision import DecisionEngine
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker


class TestDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.policy = MCPPolicyChecker()
        self.engine = DecisionEngine(self.policy, load_config())

    def test_no_mcp_actions_passes(self):
        result = self.engine.evaluate_policy(
            action_type="reply_only",
            actions=[],
            latest_msg="thanks",
        )
        self.assertTrue(result.allowed)
        self.assertIn("No MCP actions", result.reason)

    def test_blocked_tool_denied(self):
        action = MCPAction(tool="create_case_rh_portal", arguments={}, label="create")
        result = self.engine.evaluate_policy(
            action_type="call_mcp",
            actions=[action],
            latest_msg="open case",
        )
        self.assertFalse(result.allowed)
        self.assertTrue(result.reason)
        self.assertTrue(result.policy_ref.startswith("policy:"))

    def test_policy_state_mapping(self):
        result = self.engine.evaluate_policy(
            action_type="clarify",
            actions=[],
            latest_msg="which node?",
            blocked_commands=["reboot"],
        )
        state = result.to_policy_state()
        self.assertTrue(state["policy_passed"])
        self.assertEqual(state["blocked_commands"], ["reboot"])

    def test_approval_required(self):
        config = {
            "approval": {
                "enabled": True,
                "required_tools": ["oc_adm_must_gather"],
            },
        }
        engine = DecisionEngine(self.policy, config)
        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")

        with mock.patch(
            "core.decision.engine.register_pending_approvals",
            return_value=[{"fingerprint": "abc123", "tool": "oc_adm_must_gather"}],
        ):
            result = engine.evaluate_approval(
                case_id="12345",
                actions=[action],
                comment_id=1,
            )

        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_approval)
        self.assertEqual(result.approval_pending[0]["fingerprint"], "abc123")
        approval_state = result.to_approval_state()
        self.assertEqual(approval_state["action_type"], "approval_required")


if __name__ == "__main__":
    unittest.main()
