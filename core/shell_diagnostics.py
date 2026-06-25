import re
import shlex
from typing import Any, Dict, List, Optional

from core.exec_tool_adapter import EXEC_LOGICAL_TOOL
from core.mcp_action import MCPAction

# Shell diagnostics that have no dedicated MCP tool but can run via pods_exec.
SHELL_DIAG_PATTERN = re.compile(
    r"^\s*(?:nslookup|ping|dig|host|traceroute|curl)\b",
    re.I,
)

EXPLICIT_REQUEST_MARKERS = (
    "plz ",
    "please ",
    "請執行",
    "請輸出",
    "請上傳",
    "請提供",
    "請回傳",
    "run the following",
    "update the following output",
)

_CLUSTER_TOOL_MARKERS = re.compile(
    r"\b(?:oc\s+(?:get|describe|adm|logs)|kubectl\b|resources_list|pods_list|namespaces_list)",
    re.I,
)


def looks_like_explicit_support_request(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if "```" in normalized:
        return True
    if any(marker in lowered for marker in EXPLICIT_REQUEST_MARKERS):
        return True
    for line in normalized.splitlines():
        if SHELL_DIAG_PATTERN.match(line.strip()):
            return True
    return bool(SHELL_DIAG_PATTERN.search(normalized))


def extract_shell_commands_from_text(text: str) -> List[str]:
    commands: List[str] = []
    seen: set = set()

    def add(cmd: str) -> None:
        cmd = cmd.strip().strip("`")
        if cmd and cmd not in seen:
            seen.add(cmd)
            commands.append(cmd)

    for block in re.finditer(r"```[^\n]*\n(.*?)```", text, re.S):
        for line in block.group(1).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                add(line)

    for line in text.splitlines():
        line = line.strip()
        if SHELL_DIAG_PATTERN.match(line):
            add(line)

    return commands


def is_shell_only_request(text: str) -> bool:
    """True when comment asks only for host-style shell diagnostics (dig/ping/...)."""
    commands = extract_shell_commands_from_text(text)
    if not commands:
        return False
    if _CLUSTER_TOOL_MARKERS.search(text):
        return False
    return True


def is_shell_diag_mcp_action(action: MCPAction) -> bool:
    if action.tool == "exec_argv":
        argv = action.arguments.get("argv")
        if isinstance(argv, list) and argv:
            return bool(SHELL_DIAG_PATTERN.match(" ".join(str(part) for part in argv)))
    if action.tool == "pods_exec":
        command = action.arguments.get("command")
        if isinstance(command, list) and command:
            return bool(SHELL_DIAG_PATTERN.match(" ".join(str(part) for part in command)))
    return False


def needs_shell_diag_routing_override(
    mcp_calls: List[MCPAction],
    comment_text: str,
) -> bool:
    shell_commands = extract_shell_commands_from_text(comment_text)
    if not shell_commands:
        return False
    if any(is_shell_diag_mcp_action(action) for action in mcp_calls):
        return False
    return True


def infer_pods_exec_action(command: str, config: Dict[str, Any]) -> Optional[MCPAction]:
    command = command.strip()
    if not command or not SHELL_DIAG_PATTERN.match(command):
        return None

    diag = config.get("diagnostics", {}).get("pods_exec", {})
    namespace = str(diag.get("namespace", "")).strip()
    pod = str(diag.get("pod", "")).strip()
    if not namespace or not pod:
        return None

    try:
        command_argv = shlex.split(command)
    except ValueError:
        return None
    if not command_argv:
        return None

    return MCPAction(
        tool="pods_exec",
        arguments={
            "namespace": namespace,
            "name": pod,
            "command": command_argv,
        },
        label=command,
    )


def infer_exec_argv_action(command: str) -> Optional[MCPAction]:
    command = command.strip()
    if not command or not SHELL_DIAG_PATTERN.match(command):
        return None

    try:
        command_argv = shlex.split(command)
    except ValueError:
        return None
    if not command_argv:
        return None

    return MCPAction(
        tool=EXEC_LOGICAL_TOOL,
        arguments={
            "argv": command_argv,
            "timeout_seconds": 30,
        },
        label=command,
    )


def infer_shell_diag_actions(
    commands: List[str],
    config: Dict[str, Any],
    *,
    allow_host_exec: bool = False,
) -> List[MCPAction]:
    """Prefer pods_exec when configured; otherwise host exec_argv if enabled."""
    actions: List[MCPAction] = []
    for command in commands:
        action = infer_pods_exec_action(command, config)
        if action:
            actions.append(action)
            continue
        if allow_host_exec:
            host_action = infer_exec_argv_action(command)
            if host_action:
                actions.append(host_action)
    return actions


def infer_pods_exec_actions(commands: List[str], config: Dict[str, Any]) -> List[MCPAction]:
    actions: List[MCPAction] = []
    for command in commands:
        action = infer_pods_exec_action(command, config)
        if action:
            actions.append(action)
    return actions
