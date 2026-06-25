import unittest
from unittest import mock

from workflow.graph import AgentState, WorkflowDeps, build_workflow


class WorkflowAnalyzeSkipTests(unittest.TestCase):
    def test_analyze_skipped_when_prefilled(self):
        analyzer = mock.MagicMock()
        analyzer.analyze.return_value = mock.MagicMock(
            action_type="clarify",
            mcp_calls=[],
            commands=[],
            intent="unknown",
            summary="need info",
            clarifying_questions=["which node?"],
            source="llm",
            blocked_commands=[],
        )

        deps = WorkflowDeps(
            portal=mock.MagicMock(),
            executor=mock.MagicMock(),
            policy=mock.MagicMock(),
            reply_guardrail=mock.MagicMock(),
            analyzer=analyzer,
            interpreter=mock.MagicMock(),
            collaboration=mock.MagicMock(),
            convergence=mock.MagicMock(),
            composer=mock.MagicMock(),
            config={},
        )
        deps.policy.dangerous_handling = "skip_and_continue"
        deps.policy.is_dangerous_command.return_value = (False, "")
        deps.composer.compose.return_value = "clarify reply"
        deps.collaboration.reason.return_value = {
            "findings": "need node info",
            "next_steps": [],
            "customer_voice": "請問是哪個節點？",
            "source": "test",
        }

        app = build_workflow(deps)

        state: AgentState = {
            "case_id": "12345",
            "latest_msg": "please run diagnostic",
            "comment_id": 1,
            "case_history": "",
            "dry_run": True,
            "analysis_prefilled": True,
            "action_type": "clarify",
            "intent": "diagnostic",
            "request_summary": "already analyzed",
            "clarifying_questions": ["which host?"],
            "analysis_source": "llm",
            "mcp_actions": [],
            "proposed_commands": [],
            "blocked_commands": [],
        }

        output = app.invoke(state)

        analyzer.analyze.assert_not_called()
        self.assertEqual(output.get("action_type"), "clarify")
        self.assertEqual(output.get("request_summary"), "already analyzed")


if __name__ == "__main__":
    unittest.main()
