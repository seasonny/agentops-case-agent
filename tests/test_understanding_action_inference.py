import unittest

from core.config import load_config
from core.mcp_policy import MCPPolicyChecker
from core.understanding.action_inference import ActionInference

MIXED_COMMENT = """請執行

oc get pod -A
oc get nodes"""


class TestActionInference(unittest.TestCase):
    def setUp(self):
        self.inference = ActionInference(
            load_config(),
            policy=MCPPolicyChecker(),
            allow_host_exec=False,
        )

    def test_cluster_read_deterministic_route(self):
        result = self.inference.try_deterministic_route(MIXED_COMMENT)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "call_mcp")
        self.assertEqual(result.source, "route")
        self.assertEqual(len(result.mcp_calls), 2)

    def test_no_route_for_empty_comment(self):
        self.assertIsNone(self.inference.try_deterministic_route("   "))
