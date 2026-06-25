import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from core import poc_metrics
from core.comment_analyzer import CommentAnalysis
from core.mcp_action import MCPAction
from core.run_report import build_run_record, format_run_summary_human
from tests.safe_test_data import SAFE_CASE_ID, SAFE_COMMENT_ID, SAFE_SUPPORT_AUTHOR


class PocMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports_root = Path(self.tmp.name) / "reports"
        self.patch_reports = mock.patch.object(poc_metrics, "REPORTS_DIR", self.reports_root)
        self.patch_reports.start()

    def tearDown(self):
        self.patch_reports.stop()
        self.tmp.cleanup()

    def test_append_and_summarize(self):
        case_id = "12345"
        poc_metrics.append_run_record(case_id, {
            "started_at": "2026-06-25T10:00:00+00:00",
            "processing_completed": True,
            "reply_posted": True,
            "dry_run": False,
            "action_type": "call_mcp",
            "policy_passed": True,
            "response_time_seconds": 12.5,
        })
        poc_metrics.append_run_record(case_id, {
            "started_at": "2026-06-25T11:00:00+00:00",
            "processing_completed": True,
            "reply_posted": False,
            "dry_run": True,
            "action_type": "clarify",
            "policy_passed": True,
            "response_time_seconds": 5.0,
        })

        summary = poc_metrics.summarize_metrics(case_id)
        self.assertEqual(summary["total_runs"], 2)
        self.assertEqual(summary["replies_posted"], 1)
        self.assertEqual(summary["dry_runs"], 1)
        self.assertEqual(summary["clarify_count"], 1)
        self.assertAlmostEqual(summary["response_time_seconds"]["avg"], 8.75)

        text = poc_metrics.format_report_text(case_id)
        self.assertIn("Case 12345", text)
        self.assertIn("clarify 次數：1", text)

    def test_empty_report(self):
        text = poc_metrics.format_report_text("empty-case")
        self.assertIn("尚無 run 紀錄", text)


class RunReportTests(unittest.TestCase):
    def test_build_run_record_includes_policy_and_reply(self):
        analysis = CommentAnalysis(
            actionable=True,
            action_type="call_mcp",
            mcp_calls=[MCPAction(tool="pods_list", arguments={}, label="list pods")],
            intent="diagnostic",
            requires_execution=True,
            summary="List pods",
            clarifying_questions=[],
            source="llm",
        )
        comment = {
            "id": SAFE_COMMENT_ID,
            "author": SAFE_SUPPORT_AUTHOR,
            "content": "please oc get pods",
            "timestamp": "2026-06-25T09:00:00+00:00",
            "resolved_role": "support",
            "_trigger_reason": "support_request",
        }
        output = {
            "action_type": "call_mcp",
            "policy_passed": False,
            "policy_reason": "tool blocked",
            "execution_results": ["error: denied"],
            "composed_reply": "無法執行",
            "reply_posted": False,
        }
        started = datetime(2026, 6, 25, 9, 1, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 6, 25, 9, 1, 30, tzinfo=timezone.utc)

        record = build_run_record(
            case_id=SAFE_CASE_ID,
            comment=comment,
            analysis=analysis,
            output=output,
            dry_run=True,
            started_at=started,
            finished_at=finished,
        )

        self.assertEqual(record["comment_id"], SAFE_COMMENT_ID)
        self.assertFalse(record["policy_passed"])
        self.assertTrue(record["dry_run"])
        self.assertEqual(record["mcp_tools"], ["pods_list"])
        self.assertEqual(record["processing_duration_seconds"], 30.0)

        human = format_run_summary_human(record)
        self.assertIn("dry-run", human)
        self.assertIn("Policy", human)
        self.assertIn("tool blocked", human)


if __name__ == "__main__":
    unittest.main()
