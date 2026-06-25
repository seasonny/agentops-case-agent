import unittest
from unittest import mock

from core.cluster_read_routing import (
    infer_cluster_read_action,
    infer_cluster_read_actions_from_text,
    is_cluster_read_only_request,
)
from core.comment_analyzer import CommentAnalyzer
from core.config import load_config
from core.mcp_policy import MCPPolicyChecker


MIXED_COMMENT = """請執行

reboot
oc get pod -A
oc get nodes"""


class ClusterReadRoutingTests(unittest.TestCase):
    def test_oc_get_pod_all_namespaces(self):
        action = infer_cluster_read_action("oc get pod -A")
        self.assertIsNotNone(action)
        self.assertEqual(action.tool, "pods_list")
        self.assertEqual(action.arguments.get("namespace"), "")

    def test_oc_get_nodes(self):
        action = infer_cluster_read_action("oc get nodes")
        self.assertIsNotNone(action)
        self.assertEqual(action.tool, "resources_list")
        self.assertEqual(action.arguments.get("kind"), "Node")

    def test_mixed_comment_after_split_is_cluster_read_only(self):
        safe = "請執行\n\noc get pod -A\noc get nodes"
        self.assertTrue(is_cluster_read_only_request(safe))
        actions = infer_cluster_read_actions_from_text(safe)
        self.assertEqual(len(actions), 2)

    @mock.patch("core.comment_analyzer.is_llm_available", return_value=False)
    def test_mixed_dangerous_routes_without_llm(self, _mock_llm):
        config = load_config()
        analyzer = CommentAnalyzer(config, policy_checker=MCPPolicyChecker())
        result = analyzer.analyze(MIXED_COMMENT)
        self.assertEqual(result.action_type, "call_mcp")
        self.assertEqual(result.blocked_commands, ["reboot"])
        self.assertEqual(len(result.mcp_calls), 2)
        self.assertEqual(result.source, "route")


if __name__ == "__main__":
    unittest.main()
