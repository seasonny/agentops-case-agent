"""Auto-discover MCP provider binaries on PATH or via environment variables."""

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.constants import DEFAULT_MCP_CONFIG
from core.logging import log_info, log_warning

PLATFORM_COMMAND_ENV = "MCP_PLATFORM_COMMAND"
EXEC_COMMAND_ENV = "MCP_EXEC_COMMAND"

_PLATFORM_CANDIDATES = (
    "rh-tam-kubernetes-mcp-server",
    "kubernetes-mcp-server",
)

_EXEC_CANDIDATES = (
    "mcp-shell-server",
)


def _split_command(raw: str) -> List[str]:
    return [part for part in raw.strip().split() if part]


def _resolve_binary(
    env_name: str,
    candidates: tuple,
) -> Optional[str]:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        parts = _split_command(env_value)
        if parts:
            return parts[0]
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    return None


def default_exec_env() -> Dict[str, str]:
    return {
        "ALLOW_COMMANDS": "dig,ping,nslookup,host,traceroute,curl",
    }


def _venv_exec_binary() -> Optional[str]:
    """mcp-shell-server installed in the same venv as this process."""
    if not sys.executable:
        return None
    candidate = Path(sys.executable).resolve().parent / "mcp-shell-server"
    return str(candidate) if candidate.is_file() else None


def default_platform_provider() -> Dict[str, Any]:
    """npx pulls the MCP server on first use (requires Node.js + npx)."""
    fallback = DEFAULT_MCP_CONFIG["mcpServers"]["kubernetes"]
    args = fallback.get("args", [])
    if not isinstance(args, list):
        args = []
    return {
        "command": fallback["command"],
        "args": list(args),
        "env": {},
        "tool_map": {},
    }


def default_exec_provider(command: str) -> Dict[str, Any]:
    return {
        "command": command,
        "args": [],
        "env": default_exec_env(),
        "tool_map": {"exec_argv": "shell_execute"},
    }


def _resolve_exec_binary() -> Optional[str]:
    return _resolve_binary(EXEC_COMMAND_ENV, _EXEC_CANDIDATES) or _venv_exec_binary()


def build_auto_mcp_providers(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Fill missing mcp_providers: explicit config → PATH/env → product defaults."""
    providers: Dict[str, Dict[str, Any]] = {}
    raw = config.get("mcp_providers")
    if isinstance(raw, dict):
        for name, spec in raw.items():
            if isinstance(spec, dict) and spec.get("command"):
                providers[str(name)] = dict(spec)

    platform = providers.get("platform") or providers.get("kubernetes")
    if not platform:
        platform_bin = _resolve_binary(PLATFORM_COMMAND_ENV, _PLATFORM_CANDIDATES)
        if platform_bin:
            providers["platform"] = {
                "command": platform_bin,
                "args": [],
                "env": {},
                "tool_map": {},
            }
            log_info("mcp_autodiscover", provider="platform", command=platform_bin, source="path")
        else:
            providers["platform"] = default_platform_provider()
            log_info(
                "mcp_autodiscover",
                provider="platform",
                command=providers["platform"]["command"],
                args=providers["platform"]["args"],
                source="default_npx",
            )

    if "exec" not in providers:
        exec_bin = _resolve_exec_binary()
        if exec_bin:
            providers["exec"] = default_exec_provider(exec_bin)
            log_info("mcp_autodiscover", provider="exec", command=exec_bin)

    return providers


def apply_mcp_auto_discovery(config: Dict[str, Any]) -> Dict[str, Any]:
    discovered = build_auto_mcp_providers(config)
    if discovered:
        config["mcp_providers"] = discovered
    return config
