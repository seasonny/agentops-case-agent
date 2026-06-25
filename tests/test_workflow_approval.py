import unittest
from unittest import mock

from core.mcp_action import MCPAction
from workflow.graph import AgentState, WorkflowDeps, build_workflow


class WorkflowApprovalTests(unittest.TestCase):
    def test_execute_blocks_until_approved(self):
        deps = WorkflowDeps(
            portal=mock.MagicMock(),
            executor=mock.MagicMock(),
            policy=mock.MagicMock(),
            reply_guardrail=mock.MagicMock(),
            analyzer=mock.MagicMock(),
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
        )
        deps.policy.dangerous_handling = "skip_and_continue"
        deps.policy.is_dangerous_command.return_value = (False, "")
        deps.policy.check_all.return_value = (True, "Passed")
        deps.composer.compose.return_value = "waiting approval"

        with mock.patch("workflow.graph.filter_unapproved_actions") as filt, mock.patch(
            "workflow.graph.register_pending_approvals"
        ) as reg:
            action = MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather")
            filt.return_value = [action]
            reg.return_value = [{"fingerprint": "abc123", "tool": "oc_adm_must_gather"}]

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
        self.assertTrue(output.get("approval_required"))
        self.assertEqual(output.get("action_type"), "approval_required")


if __name__ == "__main__":
    unittest.main()
