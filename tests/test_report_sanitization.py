import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import memory as memory_module
from core import poc_metrics
from core.approval import save_approvals
from tests.safe_test_data import FAKE_GEMINI_KEY, FAKE_OPENAI_KEY, SAFE_CASE_ID


class ReportSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reports_root = Path(self.tmp.name) / "reports"
        self.patch_reports = mock.patch.object(poc_metrics, "REPORTS_DIR", self.reports_root)
        self.patch_reports.start()

    def tearDown(self):
        self.patch_reports.stop()
        self.tmp.cleanup()

    def test_run_artifact_redacts_secrets(self):
        secret = FAKE_OPENAI_KEY
        record = {
            "case_id": SAFE_CASE_ID,
            "started_at": "2026-06-25T10:00:00+00:00",
            "execution_results": [f"auth failed with {secret}"],
            "composed_reply_preview": f"key={FAKE_GEMINI_KEY}",
        }
        path = poc_metrics.write_run_artifact(SAFE_CASE_ID, record)
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        self.assertNotIn(FAKE_GEMINI_KEY, raw)

    def test_metrics_aggregate_redacts_secrets(self):
        poc_metrics.append_run_record(SAFE_CASE_ID, {
            "started_at": "2026-06-25T10:00:00+00:00",
            "request_preview": f"password=super-secret-not-real-value",
        })
        metrics_text = poc_metrics.metrics_path(SAFE_CASE_ID).read_text(encoding="utf-8")
        self.assertNotIn("super-secret-not-real-value", metrics_text)

    def test_approvals_redact_sensitive_arguments(self):
        with mock.patch("core.approval.APPROVAL_ROOT", self.reports_root):
            save_approvals(SAFE_CASE_ID, {
                "approved": [],
                "pending": [{
                    "tool": "pods_exec",
                    "arguments": {"api_key": "pending-secret-not-real-abcdefgh"},
                }],
            })
        raw = (self.reports_root / SAFE_CASE_ID / "approvals.json").read_text(encoding="utf-8")
        self.assertNotIn("pending-secret-not-real-abcdefgh", raw)


class MemorySanitizationTests(unittest.TestCase):
    def test_save_agent_memory_redacts_execution_results(self):
        secret = FAKE_OPENAI_KEY
        with tempfile.TemporaryDirectory() as tmp:
            mem_file = Path(tmp) / "agent_memory.json"
            with mock.patch.object(memory_module, "MEMORY_FILE", mem_file):
                memory_module.save_agent_memory({
                    "case_id": SAFE_CASE_ID,
                    "execution_results": [f"bearer {secret}"],
                    "diagnostics_history": [{
                        "arguments": {"api_key": "diag-key-not-real-abcdefgh"},
                        "result_preview": secret,
                    }],
                })
            raw = mem_file.read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            self.assertNotIn("diag-key-not-real-abcdefgh", raw)


if __name__ == "__main__":
    unittest.main()
