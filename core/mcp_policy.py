from typing import Any, Dict, List, Optional, Tuple

from core.mcp_action import MCPAction
from core.policy_compiler import CompiledPolicy, load_compiled_policy


class MCPPolicyChecker:
    def __init__(self, *, compiled: Optional[CompiledPolicy] = None):
        compiled_policy = compiled or load_compiled_policy()
        self.profile = compiled_policy.profile
        self.mode = compiled_policy.mode
        self.blocked_tools = compiled_policy.blocked_tools
        self.allowed_tools = compiled_policy.allowed_tools
        self.dangerous_commands = list(compiled_policy.dangerous_commands)
        self.pods_exec_allowed_binaries = compiled_policy.pods_exec_allowed_binaries
        self.host_exec_allowed_binaries = compiled_policy.host_exec_allowed_binaries
        self.upload_allowed_prefixes = list(compiled_policy.upload_allowed_prefixes)
        self.dangerous_handling = compiled_policy.dangerous_handling

    def is_dangerous_command(self, text: str) -> Tuple[bool, str]:
        """Check whether *text* contains a dangerous OS-level command."""
        lowered = text.lower()
        for cmd in self.dangerous_commands:
            needle = cmd.lower().strip()
            if needle in lowered:
                return True, cmd
        return False, ""

    def _argv_binary(self, argv: List[Any]) -> str:
        binary = str(argv[0]).strip().lower()
        if "/" in binary:
            binary = binary.rsplit("/", 1)[-1]
        return binary

    def _check_argv_exec(
        self,
        action: MCPAction,
        *,
        allowed_binaries: frozenset,
        tool_label: str,
    ) -> Tuple[bool, str]:
        argv = action.arguments.get("argv")
        if argv is None:
            argv = action.arguments.get("command")
        if not isinstance(argv, list) or not argv:
            return False, f"❌ 安全政策攔截：{tool_label} 缺少有效的 argv 參數。"

        binary = self._argv_binary(argv)
        if binary not in allowed_binaries:
            return (
                False,
                f"❌ 安全政策攔截：{tool_label} 不允許執行 `{binary}`。"
                f"允許的指令：{', '.join(sorted(allowed_binaries))}。",
            )

        cmd_line = " ".join(str(part) for part in argv)
        is_dangerous, matched = self.is_dangerous_command(cmd_line)
        if is_dangerous:
            return (
                False,
                f"❌ 安全政策攔截：{tool_label} argv 包含危險指令 `{matched}`。",
            )
        return True, "Passed"

    def _check_pods_exec(self, action: MCPAction) -> Tuple[bool, str]:
        command = action.arguments.get("command")
        if not isinstance(command, list) or not command:
            return False, "❌ 安全政策攔截：pods_exec 缺少有效的 command 參數。"

        binary = self._argv_binary(command)
        if binary not in self.pods_exec_allowed_binaries:
            return (
                False,
                f"❌ 安全政策攔截：pods_exec 不允許執行 `{binary}`。"
                f"允許的指令：{', '.join(sorted(self.pods_exec_allowed_binaries))}。",
            )

        cmd_line = " ".join(str(part) for part in command)
        is_dangerous, matched = self.is_dangerous_command(cmd_line)
        if is_dangerous:
            return (
                False,
                f"❌ 安全政策攔截：pods_exec command 包含危險指令 `{matched}`。",
            )
        return True, "Passed"

    def _check_exec_argv(self, action: MCPAction) -> Tuple[bool, str]:
        return self._check_argv_exec(
            action,
            allowed_binaries=self.host_exec_allowed_binaries,
            tool_label="exec_argv",
        )

    def _check_upload(self, action: MCPAction) -> Tuple[bool, str]:
        if not self.upload_allowed_prefixes:
            return True, "Passed"
        path = ""
        for key in ("file", "path", "file-path", "filepath", "file_path"):
            if key in action.arguments:
                path = str(action.arguments[key]).strip()
                break
        if not path:
            return False, "❌ 安全政策攔截：upload_attachment 缺少檔案路徑參數。"
        normalized = path.replace("\\", "/")
        for prefix in self.upload_allowed_prefixes:
            p = str(prefix).replace("\\", "/")
            if normalized.startswith(p):
                return True, "Passed"
        allowed = ", ".join(self.upload_allowed_prefixes)
        return (
            False,
            f"❌ 安全政策攔截：upload 路徑 `{path}` 不在允許前綴內（{allowed}）。",
        )

    def check_action(self, action: MCPAction) -> Tuple[bool, str]:
        if action.tool in self.blocked_tools:
            return False, f"❌ 安全政策攔截：禁止呼叫 MCP 工具 `{action.tool}`。"
        if self.mode == "allowlist" and self.allowed_tools is not None:
            if action.tool not in self.allowed_tools:
                return (
                    False,
                    f"❌ 安全政策攔截：工具 `{action.tool}` 不在允許清單內"
                    f"（profile={self.profile}, mode=allowlist）。",
                )
        if action.tool == "pods_exec":
            return self._check_pods_exec(action)
        if action.tool == "exec_argv":
            return self._check_exec_argv(action)
        if action.tool == "upload_attachment_rh_portal":
            return self._check_upload(action)
        return True, "Passed"

    def check_all(self, actions: List[MCPAction]) -> Tuple[bool, str]:
        for action in actions:
            passed, reason = self.check_action(action)
            if not passed:
                return False, reason
        return True, "Passed"


def actions_from_payload(raw_calls: Any) -> List[MCPAction]:
    if not isinstance(raw_calls, list):
        return []
    actions: List[MCPAction] = []
    for item in raw_calls:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool", "")).strip()
        if not tool:
            continue
        arguments = item.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        label = str(item.get("label", "")).strip()
        actions.append(MCPAction(tool=tool, arguments=arguments, label=label))
    return actions
