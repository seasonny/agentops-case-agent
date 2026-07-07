import unittest
from unittest import mock

from core.config import load_config
from core.mcp_policy import MCPPolicyChecker
from core.understanding import UnderstandingService

MIXED_COMMENT = """請執行

oc get pod -A
oc get nodes"""


class TestUnderstandingService(unittest.TestCase):
    def setUp(self):
        self.service = UnderstandingService(
            load_config(),
            policy_checker=MCPPolicyChecker(),
            allow_host_exec=False,
        )

    def test_empty_comment_returns_no_action(self):
        result = self.service.analyze("   ")
        self.assertFalse(result.actionable)
        self.assertEqual(result.action_type, "no_action")

    @mock.patch("core.llm_client.is_llm_available", return_value=False)
    def test_cluster_read_route_without_llm(self, _mock_llm):
        result = self.service.analyze(MIXED_COMMENT)
        self.assertTrue(result.actionable)
        self.assertEqual(result.action_type, "call_mcp")
        self.assertEqual(result.source, "route")
        self.assertEqual(len(result.mcp_calls), 2)

    def test_comment_analyzer_facade_matches_service(self):
        from core.comment_analyzer import CommentAnalyzer

        facade = CommentAnalyzer(load_config(), policy_checker=MCPPolicyChecker())
        with mock.patch("core.comment_analyzer.is_llm_available", return_value=False):
            facade_result = facade.analyze(MIXED_COMMENT)
        with mock.patch("core.llm_client.is_llm_available", return_value=False):
            service_result = self.service.analyze(MIXED_COMMENT)
        self.assertEqual(facade_result.action_type, service_result.action_type)
        self.assertEqual(facade_result.source, service_result.source)
        self.assertEqual(len(facade_result.mcp_calls), len(service_result.mcp_calls))
