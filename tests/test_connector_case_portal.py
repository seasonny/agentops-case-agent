import unittest
from unittest import mock

from connectors import CasePortalConnector


class CasePortalConnectorTests(unittest.TestCase):
    def test_poll_events_delegates_to_bridge(self):
        bridge = mock.MagicMock()
        bridge.query_case_comments.return_value = [{"id": 1, "content": "hi"}]
        connector = CasePortalConnector(bridge)

        result = connector.poll_events("12345", start_date="2026-01-01")

        bridge.query_case_comments.assert_called_once_with(
            "12345", start_date="2026-01-01"
        )
        self.assertEqual(result[0]["id"], 1)

    def test_send_response_delegates_to_bridge(self):
        bridge = mock.MagicMock()
        bridge.add_comment.return_value = {"success": True}
        connector = CasePortalConnector(bridge)

        result = connector.send_response("12345", "reply text")

        bridge.add_comment.assert_called_once_with("12345", "reply text")
        self.assertTrue(result["success"])

    def test_fetch_context_delegates_to_bridge(self):
        bridge = mock.MagicMock()
        bridge.query_case_detail.return_value = {"status": "OPEN"}
        connector = CasePortalConnector(bridge)

        result = connector.fetch_context("12345")

        bridge.query_case_detail.assert_called_once_with("12345")
        self.assertEqual(result["status"], "OPEN")

    def test_list_attachments_delegates_to_bridge(self):
        bridge = mock.MagicMock()
        bridge.list_attachments.return_value = [{"file_name": "a.tar.gz"}]
        connector = CasePortalConnector(bridge)

        result = connector.list_attachments("12345")

        bridge.list_attachments.assert_called_once_with("12345")
        self.assertEqual(result[0]["file_name"], "a.tar.gz")


if __name__ == "__main__":
    unittest.main()
