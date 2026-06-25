from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from bridges.mcp_bridge import MCPBridge
from bridges.mcp_registry import MCPRegistry
from core.exec_tool_adapter import EXEC_LOGICAL_TOOL, adapt_exec_tool_call, try_parse_shell_execute_json
from core.audit_trail import AuditTrail
from core.logging import log_info


def extract_mcp_tool_text(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)

    if "error" in result:
        return f"Error: {result['error']}"

    if result.get("isError"):
        content = result.get("content")
        if isinstance(content, list):
            return "; ".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    if result.get("output"):
        return str(result["output"])

    content = result.get("content")
    if isinstance(content, list):
        parts = [
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in content
        ]
        text = "\n".join(part for part in parts if part)
        if text:
            return try_parse_shell_execute_json(text)

    return ""


@dataclass
class MCPAction:
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    label: str = ""

    def display_label(self) -> str:
        if self.label:
            return self.label
        args_preview = ", ".join(f"{k}={v}" for k, v in list(self.arguments.items())[:3])
        return f"MCP {self.tool}({args_preview})" if args_preview else f"MCP {self.tool}"


class MCPExecutor:
    """Delegate cluster/case/exec actions to one or more MCP Server processes."""

    def __init__(
        self,
        mcp: Union[MCPBridge, MCPRegistry],
        max_output_chars: int = 8000,
        *,
        audit: Optional[AuditTrail] = None,
        comment_id: Optional[int] = None,
        dry_run: bool = False,
    ):
        self.registry: Optional[MCPRegistry] = mcp if isinstance(mcp, MCPRegistry) else None
        self.mcp = mcp if isinstance(mcp, MCPBridge) else None
        self.max_output_chars = max_output_chars
        self.audit = audit
        self.comment_id = comment_id
        self.dry_run = dry_run

    def run_action(self, action: MCPAction) -> str:
        tool_map: Dict[str, str] = {}
        if self.registry:
            bridge, _, provider_name = self.registry.resolve_call(action.tool)
            provider = self.registry.get_provider(provider_name)
            if provider:
                tool_map = provider.tool_map
        else:
            bridge = self.mcp
            provider_name = "default"

        adapted_tool, adapted_args = adapt_exec_tool_call(
            action.tool,
            action.arguments,
            tool_map,
        )

        log_info(
            "mcp_call",
            tool=action.tool,
            actual_tool=adapted_tool,
            provider=provider_name,
            arguments=adapted_args,
        )
        result = bridge.call_tool(adapted_tool, adapted_args)
        output = extract_mcp_tool_text(result)
        if not output:
            output = "(MCP 工具無文字輸出)"
        truncated = self._truncate(output)
        if self.audit:
            self.audit.record_mcp_call(
                action,
                comment_id=self.comment_id,
                provider=str(provider_name),
                actual_tool=adapted_tool,
                result_preview=truncated,
                dry_run=self.dry_run,
            )
        return truncated

    def run_many(self, actions: List[MCPAction]) -> List[str]:
        return [self.run_action(action) for action in actions]

    def _truncate(self, output: str) -> str:
        if len(output) <= self.max_output_chars:
            return output
        return (
            output[: self.max_output_chars]
            + f"\n\n...(輸出已截斷，共 {len(output)} 字元)"
        )


def build_tools_catalog(tool_names: List[str]) -> str:
    if not tool_names:
        return "(no MCP tools available)"
    return "\n".join(f"- {name}" for name in sorted(tool_names))
