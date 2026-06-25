import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.collection_flow import (
    extract_explicit_file_paths,
    extract_must_gather_artifact_path,
    find_attachment_by_filename,
    infer_must_gather_analysis,
    is_must_gather_request,
    process_post_execute_collection,
    verify_attachment_on_case,
)
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker


class CollectionFlowTests(unittest.TestCase):
    def test_must_gather_detection(self):
        self.assertTrue(is_must_gather_request("Please run must-gather"))
        self.assertTrue(is_must_gather_request("oc adm must-gather"))

    def test_extract_must_gather_path(self):
        text = "Wrote must-gather to /tmp/must-gather.local.abc/must-gather.tar.gz"
        self.assertEqual(
            extract_must_gather_artifact_path(text),
            "/tmp/must-gather.local.abc/must-gather.tar.gz",
        )

    def test_infer_must_gather_when_tool_available(self):
        policy = MCPPolicyChecker()
        inferred = infer_must_gather_analysis(
            "please upload must-gather",
            mcp_tool_names=["oc_adm_must_gather", "upload_attachment_rh_portal"],
            policy=policy,
        )
        self.assertIsNotNone(inferred)
        self.assertEqual(inferred["mcp_calls"][0].tool, "oc_adm_must_gather")

    def test_verify_attachment_on_case(self):
        portal = mock.MagicMock()
        portal.list_attachments.return_value = [
            {"file_name": "must-gather.tar.gz", "id": "1"},
        ]
        ok, detail, item = verify_attachment_on_case(
            portal, "12345", "must-gather.tar.gz"
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

            portal = mock.MagicMock()
            portal.list_attachments.return_value = [
                {"file_name": artifact.name},
            ]
            executor = mock.MagicMock()
            executor.run_action.return_value = "upload ok"

            actions = [
                MCPAction(tool="oc_adm_must_gather", arguments={}, label="gather"),
            ]
            outcome = process_post_execute_collection(
                portal=portal,
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

    def test_extract_explicit_paths(self):
        text = "upload /var/log/app.log and /tmp/out.tar.gz"
        paths = extract_explicit_file_paths(text)
        self.assertIn("/var/log/app.log", paths)
        self.assertIn("/tmp/out.tar.gz", paths)


if __name__ == "__main__":
    unittest.main()
