import unittest

from core.blocked_command_explain import (
    explain_blocked_command,
    format_blocked_commands_section,
    merge_blocked_explanation,
)
from core.mcp_policy import MCPPolicyChecker


class BlockedCommandExplainTests(unittest.TestCase):
    def setUp(self):
        self.policy = MCPPolicyChecker()

    def test_reboot_includes_reason_and_alternative(self):
        text = explain_blocked_command("reboot", self.policy)
        self.assertIn("reboot", text)
        self.assertIn("危險系統操作", text)
        self.assertIn("oc rollout restart", text)

    def test_section_lists_all_blocked_commands(self):
        section = format_blocked_commands_section(["reboot"], self.policy)
        self.assertIn("以下指令未執行", section)
        self.assertIn("政策關鍵字", section)

    def test_merge_prepends_after_prefix(self):
        reply = merge_blocked_explanation(
            "【AI 運維代理自動通知】\n已執行 oc get nodes",
            "以下指令未執行（安全政策攔截）：\n- `reboot`：測試",
        )
        self.assertLess(reply.find("以下指令未執行"), reply.find("已執行 oc get nodes"))


if __name__ == "__main__":
    unittest.main()
