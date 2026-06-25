import unittest
from unittest import mock

from core.collaboration_reply import (
    is_echo_of_support_request,
    is_hollow_acknowledgement,
    is_substantive_collaborative_reply,
    resolve_collaborative_reply,
)
from core.comment_analyzer import CommentAnalyzer
from core.config import load_config
from core.mcp_policy import MCPPolicyChecker
from core.reply_composer import ReplyComposer

SUPPORT_DIAGNOSIS = (
    "我確認是您的 ocp cluster 所在網路出現了異常，"
    "您可以請網路團隊修復再繼續測試"
)

DNS_DIAGNOSIS = (
    "我確認是您的 DNS server 出現異常，導致解析不到 api server，"
    "您可以請 DNS 團隊修復再繼續測試"
)

GOOD_DRAFT = (
    "我們理解根因是 DNS 解析異常，會請 DNS 團隊排查修復，"
    "修復後會驗證 api server 連線。"
)

HOLLOW_DRAFT = "了解，我們已收到 Support 的說明，會依建議安排後續處理，有進展時再回報。"


class CollaborationReplyTests(unittest.TestCase):
    def test_paraphrase_is_not_echo(self):
        self.assertFalse(
            is_echo_of_support_request(GOOD_DRAFT, DNS_DIAGNOSIS)
        )

    def test_verbatim_copy_is_echo(self):
        self.assertTrue(
            is_echo_of_support_request(DNS_DIAGNOSIS, DNS_DIAGNOSIS)
        )

    def test_hollow_acknowledgement_detected(self):
        self.assertTrue(is_hollow_acknowledgement(HOLLOW_DRAFT))
        self.assertFalse(is_substantive_collaborative_reply(HOLLOW_DRAFT))

    def test_good_draft_is_substantive(self):
        self.assertTrue(is_substantive_collaborative_reply(GOOD_DRAFT))

    def test_resolve_returns_empty_for_hollow(self):
        resolved = resolve_collaborative_reply(
            customer_voice=HOLLOW_DRAFT,
            findings="",
            request_summary=DNS_DIAGNOSIS,
        )
        self.assertEqual(resolved, "")

    def test_resolve_prefers_customer_voice(self):
        resolved = resolve_collaborative_reply(
            customer_voice=GOOD_DRAFT,
            findings="internal note",
            request_summary=DNS_DIAGNOSIS,
        )
        self.assertEqual(resolved, GOOD_DRAFT)

    @mock.patch("core.comment_analyzer.is_llm_available", return_value=False)
    def test_support_diagnosis_without_llm_is_reply_only(self, _mock_llm):
        analyzer = CommentAnalyzer(load_config(), policy_checker=MCPPolicyChecker())
        result = analyzer.analyze(SUPPORT_DIAGNOSIS)
        self.assertTrue(result.actionable)
        self.assertEqual(result.action_type, "reply_only")
        self.assertTrue(result.is_processable())

    def test_reply_only_uses_collaboration_draft(self):
        composer = ReplyComposer(load_config())
        reply = composer.compose(
            case_history="",
            request_summary=DNS_DIAGNOSIS,
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[],
            policy_passed=True,
            policy_reason="",
            collaboration_draft=GOOD_DRAFT,
        )
        self.assertIsNotNone(reply)
        self.assertIn("DNS", reply or "")

    @mock.patch("core.reply_composer.chat_text", return_value=None)
    def test_reply_only_without_draft_returns_none(self, _chat_text):
        composer = ReplyComposer(load_config())
        reply = composer.compose(
            case_history="",
            request_summary=DNS_DIAGNOSIS,
            action_type="reply_only",
            mcp_actions=[],
            mcp_results=[],
            policy_passed=True,
            policy_reason="",
            collaboration_draft="",
        )
        self.assertIsNone(reply)


if __name__ == "__main__":
    unittest.main()
