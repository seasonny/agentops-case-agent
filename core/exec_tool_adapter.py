import json
from typing import Any, Dict, Tuple

EXEC_LOGICAL_TOOL = "exec_argv"
DEFAULT_EXEC_REMOTE_TOOL = "shell_execute"


def adapt_exec_tool_call(
    logical_tool: str,
    arguments: Dict[str, Any],
    tool_map: Dict[str, str],
) -> Tuple[str, Dict[str, Any]]:
    """Map Agent logical exec_argv → provider-specific tool schema."""
    if logical_tool != EXEC_LOGICAL_TOOL:
        return logical_tool, arguments

    actual_tool = tool_map.get(EXEC_LOGICAL_TOOL, DEFAULT_EXEC_REMOTE_TOOL)
    argv = arguments.get("argv")
    if argv is None:
        argv = arguments.get("command")
    if not isinstance(argv, list) or not argv:
        return actual_tool, dict(arguments)

    adapted: Dict[str, Any] = {"command": [str(part) for part in argv]}
    timeout = arguments.get("timeout_seconds", arguments.get("timeout"))
    if timeout is not None:
        adapted["timeout"] = int(timeout)
    cwd = arguments.get("cwd", arguments.get("directory"))
    if cwd:
        adapted["directory"] = str(cwd)
    return actual_tool, adapted


def format_shell_execute_text(payload: Dict[str, Any]) -> str:
    """Normalize mcp-shell-server JSON into Agent execution text."""
    if payload.get("error"):
        status = payload.get("status", 1)
        stderr = payload.get("stderr", "")
        stdout = payload.get("stdout", "")
        parts = [f"exit_code: {status}", f"error: {payload['error']}"]
        if stdout:
            parts.extend(["--- stdout ---", str(stdout)])
        if stderr:
            parts.extend(["--- stderr ---", str(stderr)])
        return "\n".join(parts)

    status = payload.get("status", payload.get("exit_code", 0))
    stdout = payload.get("stdout", "")
    stderr = payload.get("stderr", "")
    lines = [f"exit_code: {status}"]
    if stdout:
        lines.extend(["--- stdout ---", str(stdout)])
    if stderr:
        lines.extend(["--- stderr ---", str(stderr)])
    return "\n".join(lines)


def try_parse_shell_execute_json(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return text
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if not isinstance(payload, dict):
        return text
    if any(key in payload for key in ("stdout", "stderr", "status", "error")):
        return format_shell_execute_text(payload)
    return text
