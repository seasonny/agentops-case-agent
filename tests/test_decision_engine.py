import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.config import load_config
from core.decision import DecisionContext, DecisionEngine
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.policy_compiler import compile_policy


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

    def test_unified_evaluate_includes_approval(self):
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
            result = engine.evaluate(
                DecisionContext(
                    action_type="call_mcp",
                    actions=[action],
                    latest_msg="must-gather",
                    case_id="12345",
                    comment_id=1,
                )
            )

        self.assertFalse(result.allowed)
        self.assertTrue(result.requires_approval)
        self.assertEqual(result.to_workflow_state()["action_type"], "approval_required")

    def test_resume_grant_bypasses_approval_in_unified_evaluate(self):
        import tempfile
        from pathlib import Path

        from core import approval as approval_mod
        from core.approval import (
            approve_fingerprint,
            persist_workflow_context_from_memory,
            register_pending_approvals,
        )

        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        config = {
            "approval": {
                "enabled": True,
                "required_tools": ["oc_adm_must_gather"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(approval_mod, "APPROVAL_ROOT", Path(tmp)):
                pending = register_pending_approvals("12345", [action], comment_id=1, config=config)
                memory = {
                    "case_id": "12345",
                    "latest_msg": "must-gather",
                    "mcp_actions": [
                        {"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"},
                    ],
                    "request_summary": "must-gather",
                    "blocked_commands": [],
                    "intent": "diagnose",
                    "analysis_source": "test",
                    "proposed_commands": [],
                    "clarifying_questions": [],
                }
                persist_workflow_context_from_memory(
                    "12345",
                    memory=memory,
                    comment={"id": 1, "content": "must-gather"},
                    pending=pending,
                )
                approved = approve_fingerprint("12345", pending[0]["fingerprint"], approved_by="sre")[1]
                engine = DecisionEngine(self.policy, config)
                result = engine.evaluate(
                    DecisionContext(
                        action_type="call_mcp",
                        actions=[action],
                        latest_msg="must-gather",
                        case_id="12345",
                        comment_id=1,
                        resume_pending_id=approved["pending_id"],
                    )
                )

        self.assertTrue(result.allowed)
        self.assertFalse(result.requires_approval)

    def test_skip_and_continue_partial_allow(self):
        mixed = """請執行

reboot
oc get pod -A
oc get nodes"""
        actions = [
            MCPAction(tool="pods_list", arguments={"namespace": ""}, label="oc get pod -A"),
            MCPAction(
                tool="resources_list",
                arguments={"apiVersion": "v1", "kind": "Node"},
                label="oc get nodes",
            ),
        ]
        result = self.engine.evaluate(
            DecisionContext(
                action_type="call_mcp",
                actions=actions,
                latest_msg=mixed,
                case_id="12345",
            )
        )
        self.assertTrue(result.allowed)
        self.assertEqual(result.blocked_commands, ["reboot"])
        self.assertEqual(len(result.allowed_actions), 2)

    def test_reject_all_blocks_entire_comment(self):
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
        engine = DecisionEngine(checker, load_config())
        mixed = """請執行

reboot
oc get pod -A"""
        result = engine.evaluate(
            DecisionContext(
                action_type="call_mcp",
                actions=[
                    MCPAction(tool="pods_list", arguments={}, label="oc get pod -A"),
                ],
                latest_msg=mixed,
                case_id="12345",
            )
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.action_type_override, "dangerous_command")
        self.assertIn("reboot", result.blocked_commands)


if __name__ == "__main__":
    unittest.main()
