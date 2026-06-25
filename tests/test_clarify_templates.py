import unittest

from core.clarify_templates import (
    detect_clarify_scenario,
    enrich_clarifying_questions,
    should_use_clarify_instead_of_reply_only,
)


class ClarifyTemplateTests(unittest.TestCase):
    def test_must_gather_no_mcp_scenario(self):
        scenario = detect_clarify_scenario(
            "Please collect must-gather",
            action_type="clarify",
            mcp_tool_names=["pods_list"],
            allow_host_exec=False,
        )
        self.assertEqual(scenario, "must_gather_no_mcp")

    def test_enrich_questions_includes_template(self):
        questions = enrich_clarifying_questions(
            "Please collect must-gather",
            action_type="clarify",
            existing_questions=[],
            mcp_tool_names=["pods_list"],
            allow_host_exec=False,
        )
        self.assertTrue(any("must-gather" in q for q in questions))
        self.assertGreaterEqual(len(questions), 2)

    def test_should_clarify_for_sosreport(self):
        self.assertTrue(
            should_use_clarify_instead_of_reply_only(
                "please run sosreport",
                mcp_tool_names=["pods_list"],
            )
        )


if __name__ == "__main__":
    unittest.main()
