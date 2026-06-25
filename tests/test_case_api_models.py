import unittest

from core.case_api_models import (
    map_created_by_type_to_role,
    normalize_api_case,
    normalize_api_comments,
    parse_case_comments_payload,
)
from core.comments import comment_handled_key
from core.participants import ParticipantResolver


class TestCaseApiModels(unittest.TestCase):
    def test_parse_hydra_comments_array(self):
        payload = [
            {
                "id": "100",
                "commentBody": "older message",
                "createdDate": "2026-06-24T10:00:00Z",
                "createdBy": "Customer User",
                "createdByType": "CUSTOMER",
            },
            {
                "id": "101",
                "commentBody": "please run oc get node",
                "createdDate": "2026-06-24T10:05:00Z",
                "createdBy": "Red Hat Engineer",
                "createdByType": "ASSOCIATE",
            },
        ]
        comments = parse_case_comments_payload(payload, case_number="01234567")
        self.assertIsNotNone(comments)
        assert comments is not None
        self.assertEqual(len(comments), 2)
        newest = comments[-1]
        self.assertEqual(newest["portal_comment_id"], "101")
        self.assertEqual(newest["id"], 1)
        self.assertEqual(newest["api_role"], "support")
        self.assertEqual(newest["content"], "please run oc get node")

    def test_skip_draft_comments(self):
        payload = [
            {
                "id": "1",
                "commentBody": "draft",
                "createdDate": "2026-06-24T10:00:00Z",
                "createdBy": "x",
                "createdByType": "CUSTOMER",
                "isDraft": True,
            }
        ]
        comments = normalize_api_comments(payload)
        self.assertEqual(comments, [])

    def test_portal_comment_dedup_key(self):
        comment = {
            "id": 1,
            "portal_comment_id": "127",
            "content": "hello",
            "timestamp": "2026-06-24T10:00:00Z",
        }
        key = comment_handled_key(comment)
        self.assertTrue(key.startswith("pid:127:"))

    def test_created_by_type_mapping(self):
        self.assertEqual(map_created_by_type_to_role("ASSOCIATE"), "support")
        self.assertEqual(map_created_by_type_to_role("CUSTOMER"), "customer")

    def test_participant_resolver_uses_api_role(self):
        config = {"participants": {"demo_trigger_prefix": ""}}
        resolver = ParticipantResolver(config)
        comment = {
            "author": "ambiguous name",
            "content": "please check nodes",
            "created_by_type": "ASSOCIATE",
            "api_role": "support",
        }
        resolver.enrich_comments([comment])
        self.assertEqual(comment["resolved_role"], "support")

    def test_normalize_case_detail(self):
        case = normalize_api_case(
            {
                "caseNumber": "01234567",
                "status": "Waiting on Customer",
                "severity": "3",
                "summary": "test",
                "product": "OCP",
                "version": "4.16",
            }
        )
        self.assertIsNotNone(case)
        assert case is not None
        self.assertEqual(case["case_number"], "01234567")
        self.assertEqual(case["status"], "Waiting on Customer")

    def test_legacy_text_returns_none(self):
        legacy = "[1] User (2026-06-24T10:00:00Z,public):\nhello"
        self.assertIsNone(parse_case_comments_payload(legacy))


if __name__ == "__main__":
    unittest.main()
