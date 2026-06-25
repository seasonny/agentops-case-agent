import unittest
from unittest import mock

from core.case_convergence import CaseConvergenceAssessor, VALID_CASE_STATUS


class CaseConvergenceTests(unittest.TestCase):
    def test_assess_resolved_when_llm_says_so(self):
        assessor = CaseConvergenceAssessor({"llm": {}})
        with mock.patch("core.case_convergence.chat_json") as chat_json:
            chat_json.return_value = {
                "converged": True,
                "case_status": "RESOLVED",
                "solution_summary": "Network ACL fixed",
                "reason": "Support confirmed fix and customer agreed",
            }
            result = assessor.assess(
                case_history="history",
                request_summary="fix network",
                interpretation_findings="ACL was wrong",
                next_steps="- verify",
            )

        self.assertTrue(result["converged"])
        self.assertEqual(result["case_status"], "RESOLVED")
        self.assertIn("ACL", result["solution_summary"])
        self.assertIn("Support confirmed", result["reason"])

    def test_fallback_when_llm_unavailable(self):
        assessor = CaseConvergenceAssessor({"llm": {}})
        with mock.patch("core.case_convergence.chat_json", return_value=None):
            result = assessor.assess(
                case_history="",
                request_summary="",
                interpretation_findings="",
                next_steps="",
            )
        self.assertFalse(result["converged"])
        self.assertEqual(result["case_status"], "POLLING")
        self.assertEqual(result["source"], "fallback")

    def test_invalid_status_normalized_to_polling(self):
        assessor = CaseConvergenceAssessor({"llm": {}})
        with mock.patch("core.case_convergence.chat_json") as chat_json:
            chat_json.return_value = {
                "converged": False,
                "case_status": "UNKNOWN",
                "reason": "still investigating",
            }
            result = assessor.assess(
                case_history="",
                request_summary="",
                interpretation_findings="",
                next_steps="",
            )
        self.assertEqual(result["case_status"], "POLLING")
        self.assertIn(result["case_status"], VALID_CASE_STATUS)


if __name__ == "__main__":
    unittest.main()
