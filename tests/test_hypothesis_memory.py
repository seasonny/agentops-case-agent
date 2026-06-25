import unittest

from core.case_context_memory import (
    augment_case_history,
    format_hypothesis_context,
    record_hypothesis,
)


class HypothesisMemoryTests(unittest.TestCase):
    def test_record_and_format_hypothesis(self):
        memory = {}
        record_hypothesis(
            memory,
            comment_id=218,
            request_summary="DNS server 異常",
            diagnosis_understanding="DNS 解析失敗導致 api server 不可達",
            customer_actions=["聯繫 DNS 團隊修復"],
            confirmation_questions=["修復後是否需驗證其他 endpoint？"],
            verification_plan="修復後測試 api server DNS 解析",
            convergence_signal="partial",
            customer_voice="我們理解是 DNS 問題，會請 DNS 團隊修復。",
        )
        ctx = format_hypothesis_context(memory)
        self.assertIn("DNS 解析失敗", ctx)
        self.assertIn("partial", ctx)
        self.assertIn("聯繫 DNS 團隊", ctx)

    def test_augment_case_history_includes_hypothesis(self):
        memory = {}
        record_hypothesis(
            memory,
            comment_id=1,
            request_summary="test",
            diagnosis_understanding="network issue",
            customer_actions=["fix network"],
        )
        augmented = augment_case_history("Case thread", memory)
        self.assertIn("Case thread", augmented)
        self.assertIn("network issue", augmented)


if __name__ == "__main__":
    unittest.main()
