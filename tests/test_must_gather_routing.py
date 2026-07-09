import unittest
from unittest import mock

from core.config import load_config
from core.mcp_policy import MCPPolicyChecker
from core.understanding import UnderstandingService


class MustGatherCatalogRouteTests(unittest.TestCase):
    def setUp(self):
        self.service = UnderstandingService(
            load_config(),
            mcp_tool_names=["oc_adm_must_gather", "pods_list"],
            policy_checker=MCPPolicyChecker(),
        )

    def test_clarify_coerced_to_must_gather_when_tool_in_catalog(self):
        llm_payload = {
            "actionable": True,
            "action_type": "clarify",
            "mcp_calls": [],
            "intent": "diagnostic",
            "summary": "No must-gather tool available",
            "clarifying_questions": ["Which namespace?"],
        }

        def fake_chat(*_args, **_kwargs):
            return llm_payload

        with mock.patch("core.llm_client.is_llm_available", return_value=True):
            result = self.service.analyze(
                "請上傳 must-gather",
                chat_fn=fake_chat,
                is_llm_available_fn=lambda _cfg: True,
            )

        self.assertEqual(result.action_type, "call_mcp")
        self.assertEqual(result.source, "must_gather_catalog_route")
        self.assertEqual(len(result.mcp_calls), 1)
        self.assertEqual(result.mcp_calls[0].tool, "oc_adm_must_gather")

    def test_no_coercion_when_tool_not_in_catalog(self):
        service = UnderstandingService(
            load_config(),
            mcp_tool_names=["pods_list"],
            policy_checker=MCPPolicyChecker(),
        )
        llm_payload = {
            "actionable": True,
            "action_type": "clarify",
            "mcp_calls": [],
            "intent": "diagnostic",
            "summary": "Need steps",
            "clarifying_questions": ["Which path?"],
        }

        with mock.patch("core.llm_client.is_llm_available", return_value=True):
            result = service.analyze(
                "請上傳 must-gather",
                chat_fn=lambda *_a, **_k: llm_payload,
                is_llm_available_fn=lambda _cfg: True,
            )

        self.assertEqual(result.action_type, "clarify")
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.mcp_calls, [])


if __name__ == "__main__":
    unittest.main()
