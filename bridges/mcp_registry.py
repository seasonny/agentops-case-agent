from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from bridges.mcp_bridge import MCPBridge
from core.logging import log_info, log_warning


@dataclass
class MCPProvider:
    name: str
    bridge: MCPBridge
    tool_map: Dict[str, str] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)

    def resolve_tool(self, logical_tool: str) -> Tuple[str, bool]:
        """Return (actual_tool_name, mapped)."""
        actual = self.tool_map.get(logical_tool)
        if actual:
            return actual, True
        return logical_tool, False


class MCPRegistry:
    """Route MCP tool calls to the correct provider process."""

    def __init__(self, providers: Dict[str, MCPProvider]):
        self.providers = providers
        self._logical_to_provider: Dict[str, str] = {}
        self._build_routing_index()

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "MCPRegistry":
        from core.config import iter_mcp_provider_specs

        providers: Dict[str, MCPProvider] = {}
        for name, spec in iter_mcp_provider_specs(config).items():
            command = spec.get("command")
            if not command:
                log_warning("mcp_provider_skipped", provider=name, reason="missing_command")
                continue
            args = spec.get("args", [])
            if not isinstance(args, list):
                args = []
            env = spec.get("env", {})
            if not isinstance(env, dict):
                env = {}
            tool_map = spec.get("tool_map", {})
            if not isinstance(tool_map, dict):
                tool_map = {}
            tools = spec.get("tools", [])
            if not isinstance(tools, list):
                tools = []

            bridge = MCPBridge(
                [command, *args],
                env={str(k): str(v) for k, v in env.items()},
                provider_name=name,
            )
            providers[name] = MCPProvider(
                name=name,
                bridge=bridge,
                tool_map={str(k): str(v) for k, v in tool_map.items()},
                tools=[str(t) for t in tools],
            )
            log_info(
                "mcp_provider_registered",
                provider=name,
                tool_map=tool_map or None,
                started=bridge.proc is not None,
            )
        return cls(providers)

    def _build_routing_index(self) -> None:
        self._logical_to_provider.clear()
        for provider_name, provider in self.providers.items():
            for logical in provider.tool_map:
                self._logical_to_provider[logical] = provider_name
            for tool in provider.tools:
                self._logical_to_provider.setdefault(tool, provider_name)

    def get_provider(self, name: str) -> Optional[MCPProvider]:
        return self.providers.get(name)

    def platform_bridge(self) -> MCPBridge:
        for key in ("platform", "case", "cluster", "kubernetes"):
            provider = self.providers.get(key)
            if provider and provider.bridge.proc:
                return provider.bridge
        for provider in self.providers.values():
            if provider.name != "exec" and provider.bridge.proc:
                return provider.bridge
        for provider in self.providers.values():
            if provider.bridge.proc:
                return provider.bridge
        return next(iter(self.providers.values())).bridge if self.providers else MCPBridge(["false"])

    def has_exec_provider(self) -> bool:
        return "exec" in self.providers and self.providers["exec"].bridge.proc is not None

    def resolve_call(self, logical_tool: str) -> Tuple[MCPBridge, str, str]:
        """Return (bridge, actual_tool_name, provider_name)."""
        provider_name = self._logical_to_provider.get(logical_tool)
        if provider_name:
            provider = self.providers[provider_name]
            actual, _ = provider.resolve_tool(logical_tool)
            return provider.bridge, actual, provider_name

        if logical_tool == "exec_argv" and "exec" in self.providers:
            provider = self.providers["exec"]
            actual, _ = provider.resolve_tool(logical_tool)
            return provider.bridge, actual, "exec"

        bridge = self.platform_bridge()
        provider_name = next(
            (p.name for p in self.providers.values() if p.bridge is bridge),
            "platform",
        )
        return bridge, logical_tool, provider_name

    def list_tools(self) -> List[str]:
        names: List[str] = []
        seen: set = set()
        for provider in self.providers.values():
            for tool in provider.bridge.list_tools():
                if tool and tool not in seen:
                    seen.add(tool)
                    names.append(tool)
            for logical in provider.tool_map:
                if logical not in seen:
                    seen.add(logical)
                    names.append(logical)
        return sorted(names)

    def close(self) -> None:
        for provider in self.providers.values():
            provider.bridge.close()
