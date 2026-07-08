import tempfile
import unittest
from pathlib import Path
from unittest import mock

from domain.case.collection_flow import (
    extract_must_gather_artifact_path,
    find_attachment_by_filename,
    process_post_execute_collection,
    verify_attachment_on_case,
)
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker


class CollectionFlowTests(unittest.TestCase):
    def test_extract_must_gather_path(self):
        text = "Wrote must-gather to /tmp/must-gather.local.abc/must-gather.tar.gz"
        self.assertEqual(
            extract_must_gather_artifact_path(text),
            "/tmp/must-gather.local.abc/must-gather.tar.gz",
        )

    def test_verify_attachment_on_case(self):
        connector = mock.MagicMock()
        connector.list_attachments.return_value = [
            {"file_name": "must-gather.tar.gz", "id": "1"},
        ]
        ok, detail, item = verify_attachment_on_case(
            connector, "12345", "must-gather.tar.gz"
        )
        self.assertTrue(ok)
        self.assertIn("must-gather", detail)
        self.assertIsNotNone(item)

    def test_find_attachment_by_filename_partial(self):
        attachments = [{"file_name": "diag-123-must-gather.tar.gz"}]
        matched = find_attachment_by_filename(attachments, "must-gather.tar.gz")
        self.assertIsNotNone(matched)

    def test_must_gather_follow_up_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "must-gather.tar.gz"
            artifact.write_text("data", encoding="utf-8")
            gather_output = f"saved to {artifact}"

            connector = mock.MagicMock()
            connector.list_attachments.return_value = [
                {"file_name": artifact.name},
            ]
            executor = mock.MagicMock()
            executor.run_action.return_value = "upload ok"

            actions = [
                MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather"),
            ]
            outcome = process_post_execute_collection(
                connector=connector,
                executor=executor,
                policy=MCPPolicyChecker(),
                case_id="999",
                actions=actions,
                execution_results=[gather_output],
                dry_run=False,
            )

            self.assertTrue(outcome["collection_uploaded"])
            self.assertTrue(outcome["attachment_verified"])
            executor.run_action.assert_called_once()


if __name__ == "__main__":
    unittest.main()
