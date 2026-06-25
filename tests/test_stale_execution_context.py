import unittest
from unittest import mock

from core.comment_analyzer import CommentAnalyzer
from core.config import load_config
from core.mcp_policy import MCPPolicyChecker
from core.collaboration_reply import is_echo_of_support_request
from core.reply_composer import ReplyComposer
from core.reply_guardrail import ReplyGuardrail
from core.turn_context import mcp_results_for_compose, reset_turn_execution_state

SUPPORT_DIAGNOSIS = (
    "我確認是您的 ocp cluster 所在網路出現了異常，"
    "您可以請網路團隊修復再繼續測試"
)

STALE_DIG = (
    "; <<>> DiG 9.10.6 <<>> google.com.tw\n"
    ";; ANSWER SECTION:\ngoogle.com.tw.\t\t300\tIN\tA\t142.250.192.131"
)


class StaleExecutionContextTests(unittest.TestCase):
    def test_mcp_results_for_compose_strips_stale_on_reply_only(self):
        results = mcp_results_for_compose(
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[STALE_DIG],
        )
        self.assertEqual(results, [])

    def test_reset_turn_execution_state_clears_prior_output(self):
        memory = {
            "execution_results": [STALE_DIG],
            "interpretation_findings": "old",
            "all_mcp_actions": [{"tool": "exec_argv", "arguments": {}, "label": "dig"}],
        }
        reset_turn_execution_state(memory, action_type="reply_only", mcp_actions=[])
        self.assertEqual(memory["execution_results"], [])
        self.assertEqual(memory["all_mcp_actions"], [])
        self.assertEqual(memory["interpretation_findings"], "")

    def test_echo_of_support_detected(self):
        self.assertTrue(
            is_echo_of_support_request(
                SUPPORT_DIAGNOSIS,
                SUPPORT_DIAGNOSIS,
            )
        )

    @mock.patch("core.reply_composer.chat_text", return_value=None)
    def test_reply_only_without_draft_returns_none(self, _chat_text):
        composer = ReplyComposer(load_config())
        reply = composer.compose(
            case_history="",
            request_summary=SUPPORT_DIAGNOSIS,
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[],
            policy_passed=True,
            policy_reason="",
            collaboration_draft="",
        )
        self.assertIsNone(reply)

    @mock.patch("core.reply_composer.chat_text", return_value=None)
    def test_reply_only_hollow_draft_returns_none(self, _chat_text):
        composer = ReplyComposer(load_config())
        reply = composer.compose(
            case_history="",
            request_summary=SUPPORT_DIAGNOSIS,
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[],
            policy_passed=True,
            policy_reason="",
            collaboration_draft="了解，我們已收到 Support 的說明，會依建議安排後續處理，有進展時再回報。",
        )
        self.assertIsNone(reply)

    @mock.patch("core.reply_composer.chat_text")
    def test_reply_only_uses_collaboration_draft_when_compose_skipped(self, chat_text):
        chat_text.return_value = None
        composer = ReplyComposer(load_config())
        reply = composer.compose(
            case_history="",
            request_summary=SUPPORT_DIAGNOSIS,
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[],
            policy_passed=True,
            policy_reason="",
            collaboration_draft="了解，我們會請網路團隊協助修復，完成後再依指示測試。",
        )
        self.assertIsNotNone(reply)
        self.assertIn("網路團隊", reply or "")
        chat_text.assert_not_called()

    @mock.patch("core.reply_composer.chat_text")
    def test_reply_only_compose_does_not_call_llm(self, chat_text):
        chat_text.return_value = (
            "【AI 運維代理自動通知】\n"
            "了解，我們會請網路團隊協助修復，完成後再依指示繼續測試。"
        )
        composer = ReplyComposer(load_config())
        composer.compose(
            case_history="",
            request_summary=SUPPORT_DIAGNOSIS,
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[STALE_DIG],
            policy_passed=True,
            policy_reason="",
            collaboration_draft="了解，我們會請網路團隊協助修復，完成後再依指示繼續測試。",
        )
        chat_text.assert_not_called()

    def test_guardrail_blocks_diagnostic_dump_on_reply_only(self):
        guardrail = ReplyGuardrail(load_config())
        passed, reason, _ = guardrail.validate(
            "【AI 運維代理自動通知】\n" + STALE_DIG,
            action_type="reply_only",
            execution_results=[],
        )
        self.assertFalse(passed)
        self.assertEqual(reason, "text_only_turn_with_execution_output")

    @mock.patch("core.comment_analyzer.is_llm_available", return_value=False)
    def test_support_diagnosis_routes_reply_only(self, _mock_llm):
        analyzer = CommentAnalyzer(load_config(), policy_checker=MCPPolicyChecker())
        result = analyzer.analyze(SUPPORT_DIAGNOSIS)
        self.assertEqual(result.action_type, "reply_only")


if __name__ == "__main__":
    unittest.main()
