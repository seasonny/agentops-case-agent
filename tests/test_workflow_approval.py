import unittest
from unittest import mock

from core.decision.models import DecisionResult
from core.mcp_action import MCPAction
from domain.case import CaseDomainHooks
from workflow.graph import AgentState, WorkflowDeps, build_workflow


class WorkflowApprovalTests(unittest.TestCase):
    def test_execute_blocks_until_approved(self):
        deps = WorkflowDeps(
            connector=mock.MagicMock(),
            executor=mock.MagicMock(),
            policy=mock.MagicMock(),
            decision_engine=mock.MagicMock(),
            reply_guardrail=mock.MagicMock(),
            understanding=mock.MagicMock(),
            interpreter=mock.MagicMock(),
            collaboration=mock.MagicMock(),
            convergence=mock.MagicMock(),
            composer=mock.MagicMock(),
            config={
                "approval": {
                    "enabled": True,
                    "required_tools": ["oc_adm_must_gather"],
                },
                "diagnostics": {"bundle_output": {"mode": "off"}},
            },
            domain_hooks=CaseDomainHooks(
                {
                    "approval": {
                        "enabled": True,
                        "required_tools": ["oc_adm_must_gather"],
                    },
                    "diagnostics": {"bundle_output": {"mode": "off"}},
                }
            ),
        )
        deps.policy.dangerous_handling = "skip_and_continue"
        deps.policy.is_dangerous_command.return_value = (False, "")
        deps.policy.check_all.return_value = (True, "Passed")
        deps.decision_engine.evaluate_policy.return_value = DecisionResult(
            allowed=True,
            reason="Passed",
            policy_ref="policy:test",
        )
        deps.composer.compose.return_value = "waiting approval"

        action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
        approval_result = mock.MagicMock()
        approval_result.allowed = False
        approval_result.to_approval_state.return_value = {
            "execution_results": [],
            "approval_required": True,
            "approval_pending": [{"fingerprint": "abc123", "tool": "oc_adm_must_gather"}],
            "action_type": "approval_required",
            "status": "POLLING",
        }
        deps.decision_engine.evaluate_approval.return_value = approval_result

        app = build_workflow(deps)
        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "must-gather",
            "comment_id": 1,
            "case_history": "",
            "dry_run": True,
            "analysis_prefilled": True,
            "action_type": "call_mcp",
            "policy_passed": True,
            "mcp_actions": [{"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"}],
            "blocked_commands": [],
        }
        output = app.invoke(state)

        deps.executor.run_many.assert_not_called()
        deps.decision_engine.evaluate_approval.assert_called_once()
        self.assertTrue(output.get("approval_required"))
        self.assertEqual(output.get("action_type"), "approval_required")


if __name__ == "__main__":
    unittest.main()
