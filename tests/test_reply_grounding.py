import unittest

from core.agent_settings import init_agent_settings
from core.comment_analyzer import CommentAnalyzer
from core.config import load_config
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.reply_grounding import (
    build_grounded_fallback_reply,
    check_execution_grounding,
    has_substantive_overlap,
)
from core.reply_guardrail import ReplyGuardrail
from core.shell_diagnostics import (
    is_shell_only_request,
    needs_shell_diag_routing_override,
)


class ReplyGroundingTests(unittest.TestCase):
    def test_detects_fabricated_dig_on_failure(self):
        results = [
            'failed to list namespaces: dial tcp: lookup api.example.com: no such host'
        ]
        reply = (
            "【AI】dig 結果如下：\n"
            "; <<>> DiG 9.16.23 <<>> google.com.tw\n"
            ";; ANSWER SECTION:\ngoogle.com.tw. 300 IN A 142.250.191.14"
        )
        passed, reason = check_execution_grounding(
            reply,
            action_type="call_mcp",
            execution_results=results,
        )
        self.assertFalse(passed)
        self.assertEqual(reason, "ungrounded_execution_output:success_claim_on_failure")

    def test_allows_grounded_output(self):
        results = [
            "exit_code: 0\n--- stdout ---\n;; ANSWER SECTION:\nexample.com. 300 IN A 93.184.216.34"
        ]
        reply = "執行結果：\n;; ANSWER SECTION:\nexample.com. 300 IN A 93.184.216.34"
        passed, _ = check_execution_grounding(
            reply,
            action_type="call_mcp",
            execution_results=results,
        )
        self.assertTrue(passed)
        self.assertTrue(has_substantive_overlap(reply, results))

    def test_skips_reply_only(self):
        passed, reason = check_execution_grounding(
            ";; ANSWER SECTION:",
            action_type="reply_only",
            execution_results=[],
        )
        self.assertTrue(passed)
        self.assertEqual(reason, "skipped_action_type")

    def test_fallback_quotes_real_output(self):
        text = build_grounded_fallback_reply(
            reply_prefix="【AI】",
            request_summary="dig test",
            mcp_actions=[
                MCPAction(tool="exec_argv", arguments={"argv": ["dig", "x.com"]}, label="dig x.com")
            ],
            execution_results=["exit_code: 0\n--- stdout ---\nok"],
        )
        self.assertIn("exit_code: 0", text)
        self.assertIn("dig x.com", text)


class ReplyGuardrailGroundingTests(unittest.TestCase):
    def setUp(self):
        config = load_config()
        init_agent_settings(config)
        self.guard = ReplyGuardrail(config, policy_checker=MCPPolicyChecker())

    def test_blocks_ungrounded_llm_reply(self):
        reply = ";; ANSWER SECTION:\nfake.example.com. 60 IN A 1.2.3.4"
        passed, reason, _ = self.guard.validate(
            reply,
            action_type="call_mcp",
            execution_results=["Error: MCP server not available"],
        )
        self.assertFalse(passed)
        self.assertTrue(reason.startswith("ungrounded_execution_output"))

    def test_grounded_fallback_passes_with_skip(self):
        fallback = build_grounded_fallback_reply(
            reply_prefix="【AI】",
            request_summary="dig",
            mcp_actions=[],
            execution_results=["exit_code: 1\nerror: command failed"],
        )
        passed, _, safe = self.guard.validate(
            fallback,
            action_type="call_mcp",
            execution_results=["exit_code: 1\nerror: command failed"],
            skip_grounding=True,
        )
        self.assertTrue(passed)
        self.assertIn("exit_code: 1", safe)


class ShellRoutingTests(unittest.TestCase):
    def test_shell_only_request(self):
        self.assertTrue(is_shell_only_request("[SE] 請執行\ndig www.google.com.tw"))
        self.assertFalse(is_shell_only_request("請執行 oc get node"))

    def test_routing_override_when_llm_picks_cluster_tools(self):
        self.assertTrue(
            needs_shell_diag_routing_override(
                [MCPAction(tool="namespaces_list", arguments={})],
                "dig www.google.com.tw",
            )
        )
        self.assertFalse(
            needs_shell_diag_routing_override(
                [MCPAction(tool="exec_argv", arguments={"argv": ["dig", "x.com"]})],
                "dig www.google.com.tw",
            )
        )

    def test_deterministic_route_skips_wrong_llm_tools(self):
        config = load_config()
        init_agent_settings(config)
        analyzer = CommentAnalyzer(
            config,
            mcp_tool_names=["exec_argv", "namespaces_list"],
            policy_checker=MCPPolicyChecker(),
            allow_host_exec=True,
        )
        result = analyzer.analyze("[SE] 請執行\ndig www.google.com.tw")
        self.assertEqual(result.action_type, "call_mcp")
        self.assertEqual(result.source, "route")
        self.assertEqual(result.mcp_calls[0].tool, "exec_argv")


if __name__ == "__main__":
    unittest.main()
