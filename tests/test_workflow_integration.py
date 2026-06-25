import unittest
from unittest import mock

from core.mcp_action import MCPAction
from workflow.graph import AgentState, WorkflowDeps, build_workflow


def _base_deps(**overrides):
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
        config={"diagnostics": {"bundle_output": {"mode": "off"}}},
    )
    deps.policy.dangerous_handling = "skip_and_continue"
    deps.policy.is_dangerous_command.return_value = (False, "")
    deps.policy.check_all.return_value = (True, "Passed")
    deps.policy.check_action.return_value = (True, "Passed")
    deps.composer.compose.return_value = "composed reply"
    deps.reply_guardrail.validate.return_value = (True, "ok", "safe reply")
    deps.interpreter.interpret.return_value = {
        "findings": "ok",
        "next_steps": [],
        "confidence": "high",
        "needs_more_evidence": False,
        "follow_up_mcp_calls": [],
        "source": "test",
    }
    deps.collaboration.reason.return_value = {
        "findings": "customer will engage network team",
        "next_steps": ["network fix"],
        "customer_voice": "了解，我們會請網路團隊協助修復後再測試。",
        "source": "test",
    }
    deps.convergence.assess.return_value = {
        "case_status": "POLLING",
        "converged": False,
        "reason": "still open",
        "solution_summary": "",
    }
    for key, value in overrides.items():
        setattr(deps, key, value)
    return deps


class WorkflowIntegrationTests(unittest.TestCase):
    def test_reply_only_runs_collaborate_convergence_before_compose(self):
        deps = _base_deps()
        deps.composer.compose.return_value = "collaborative reply"
        app = build_workflow(deps)

        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "網路異常請修復",
            "comment_id": 7,
            "case_history": "",
            "dry_run": True,
            "analysis_prefilled": True,
            "action_type": "reply_only",
            "policy_passed": True,
            "mcp_actions": [],
            "blocked_commands": [],
            "request_summary": "網路異常請修復",
        }

        output = app.invoke(state)
        deps.collaboration.reason.assert_called_once()
        deps.convergence.assess.assert_called_once()
        deps.interpreter.interpret.assert_not_called()
        self.assertEqual(output.get("composed_reply"), "collaborative reply")

        deps = _base_deps()
        deps.policy.check_all.return_value = (False, "blocked by policy")
        deps.composer.compose.return_value = "policy blocked reply"
        app = build_workflow(deps)

        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "run diag",
            "comment_id": 1,
            "case_history": "",
            "dry_run": True,
            "analysis_prefilled": True,
            "action_type": "call_mcp",
            "mcp_actions": [{"tool": "pods_list", "arguments": {}, "label": "pods"}],
            "policy_passed": True,
            "blocked_commands": [],
        }

        output = app.invoke(state)
        deps.executor.run_many.assert_not_called()
        deps.interpreter.interpret.assert_not_called()
        self.assertEqual(output.get("composed_reply"), "policy blocked reply")

    def test_dangerous_command_routes_to_compose(self):
        deps = _base_deps()
        deps.composer.compose.return_value = "dangerous blocked"
        app = build_workflow(deps)

        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "reboot the node",
            "comment_id": 2,
            "case_history": "",
            "dry_run": True,
            "analysis_prefilled": True,
            "action_type": "dangerous_command",
            "dangerous_command_blocked": True,
            "policy_passed": False,
            "policy_reason": "blocked",
            "blocked_commands": ["reboot"],
            "mcp_actions": [],
        }

        output = app.invoke(state)
        deps.executor.run_many.assert_not_called()
        self.assertEqual(output.get("composed_reply"), "dangerous blocked")

    def test_collection_node_runs_after_execute(self):
        deps = _base_deps()
        deps.executor.run_many.return_value = [
            "saved to /tmp/must-gather.local.abc/must-gather.tar.gz"
        ]
        deps.composer.compose.return_value = "upload done"
        app = build_workflow(deps)

        with mock.patch("workflow.graph.process_post_execute_collection") as proc:
            proc.return_value = {
                "collection_uploaded": True,
                "collection_upload_filename": "must-gather.tar.gz",
                "collection_upload_path": "/tmp/x/must-gather.tar.gz",
                "collection_upload_result": "ok",
                "attachment_verified": True,
                "attachment_verify_detail": "found",
            }
            state: AgentState = {
                "case_id": "12345",
                "latest_msg": "must-gather",
                "comment_id": 3,
                "case_history": "",
                "dry_run": False,
                "analysis_prefilled": True,
                "action_type": "call_mcp",
                "policy_passed": True,
                "mcp_actions": [
                    {"tool": "oc_adm_must_gather", "arguments": {}, "label": "gather"},
                ],
                "blocked_commands": [],
            }
            app.invoke(state)

        proc.assert_called_once()
        deps.executor.run_many.assert_called_once()

    def test_resolved_status_adds_convergence_reason_to_reply(self):
        deps = _base_deps()
        deps.executor.run_many.return_value = ["ok"]
        deps.composer.compose.return_value = "base reply"
        deps.convergence.assess.return_value = {
            "case_status": "RESOLVED",
            "converged": True,
            "reason": "customer confirmed fix",
            "solution_summary": "fixed ACL",
        }
        app = build_workflow(deps)

        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "oc get pods",
            "comment_id": 4,
            "case_history": "",
            "dry_run": True,
            "analysis_prefilled": True,
            "action_type": "call_mcp",
            "policy_passed": True,
            "mcp_actions": [
                {"tool": "pods_list", "arguments": {}, "label": "pods"},
            ],
            "all_mcp_actions": [
                {"tool": "pods_list", "arguments": {}, "label": "pods"},
            ],
            "investigate_step": 0,
            "blocked_commands": [],
        }

        output = app.invoke(state)
        reply = output.get("composed_reply", "")
        self.assertEqual(output.get("status"), "RESOLVED")
        self.assertIn("收斂判定", reply)
        self.assertIn("customer confirmed fix", reply)
        deps.interpreter.interpret.assert_called_once()

    def test_investigate_loop_runs_follow_up_execute(self):
        deps = _base_deps(
            config={
                "diagnostics": {"bundle_output": {"mode": "off"}},
                "investigation": {"enabled": True, "max_follow_up_steps": 2},
            }
        )
        deps.executor.run_many.side_effect = [["first batch"], ["second batch"]]
        deps.interpreter.interpret.side_effect = [
            {
                "findings": "need logs",
                "next_steps": ["check logs"],
                "confidence": "medium",
                "needs_more_evidence": True,
                "follow_up_mcp_calls": [
                    MCPAction(tool="pods_log", arguments={"name": "x"}, label="logs"),
                ],
                "source": "llm",
            },
            {
                "findings": "done",
                "next_steps": [],
                "confidence": "high",
                "needs_more_evidence": False,
                "follow_up_mcp_calls": [],
                "source": "llm",
            },
        ]
        deps.composer.compose.return_value = "investigated reply"
        app = build_workflow(deps)

        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "check pods",
            "comment_id": 5,
            "case_history": "",
            "dry_run": False,
            "analysis_prefilled": True,
            "action_type": "call_mcp",
            "policy_passed": True,
            "mcp_actions": [{"tool": "pods_list", "arguments": {}, "label": "pods"}],
            "all_mcp_actions": [{"tool": "pods_list", "arguments": {}, "label": "pods"}],
            "investigate_step": 0,
            "blocked_commands": [],
        }

        output = app.invoke(state)
        self.assertEqual(deps.executor.run_many.call_count, 2)
        self.assertEqual(deps.interpreter.interpret.call_count, 2)
        self.assertEqual(output.get("investigate_step"), 1)
        self.assertEqual(output.get("execution_results"), ["first batch", "second batch"])
        self.assertEqual(output.get("composed_reply"), "investigated reply")

    def test_investigate_policy_blocked_still_composes(self):
        deps = _base_deps(
            config={
                "diagnostics": {"bundle_output": {"mode": "off"}},
                "investigation": {"enabled": True, "max_follow_up_steps": 2},
            }
        )
        deps.executor.run_many.return_value = ["first batch"]
        deps.policy.check_all.side_effect = [(True, "Passed"), (False, "blocked follow-up")]
        deps.interpreter.interpret.return_value = {
            "findings": "need more",
            "next_steps": [],
            "confidence": "medium",
            "needs_more_evidence": True,
            "follow_up_mcp_calls": [
                MCPAction(tool="pods_log", arguments={}, label="logs"),
            ],
            "source": "llm",
        }
        deps.composer.compose.return_value = "partial reply"
        app = build_workflow(deps)

        with mock.patch("workflow.graph.process_post_execute_collection") as proc:
            proc.return_value = {
                "collection_uploaded": False,
                "collection_upload_filename": "",
                "collection_upload_path": "",
                "collection_upload_result": "",
                "attachment_verified": False,
                "attachment_verify_detail": "",
            }
            state: AgentState = {
                "case_id": "12345",
                "latest_msg": "check pods",
                "comment_id": 6,
                "case_history": "",
                "dry_run": False,
                "analysis_prefilled": True,
                "action_type": "call_mcp",
                "policy_passed": True,
                "mcp_actions": [{"tool": "pods_list", "arguments": {}, "label": "pods"}],
                "all_mcp_actions": [{"tool": "pods_list", "arguments": {}, "label": "pods"}],
                "investigate_step": 0,
                "blocked_commands": [],
            }

            output = app.invoke(state)

        self.assertEqual(deps.executor.run_many.call_count, 1)
        self.assertEqual(output.get("composed_reply"), "partial reply")
        self.assertEqual(output.get("execution_results"), ["first batch"])


if __name__ == "__main__":
    unittest.main()
