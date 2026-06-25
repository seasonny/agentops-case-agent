"""Optional: spill long MCP output to an attachment instead of the case comment."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from core.blocked_command_explain import explain_blocked_command
from core.config import PROJECT_ROOT
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker

_EXEC_DIAG_TOOLS = frozenset({"exec_argv", "pods_exec"})
_VALID_BUNDLE_MODES = frozenset({"off", "overflow_only"})


def is_exec_diag_action(action: MCPAction) -> bool:
    return action.tool in _EXEC_DIAG_TOOLS


def bundle_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = config.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    raw = diagnostics.get("bundle_output", {})
    if not isinstance(raw, dict):
        raw = {}
    defaults = {
        "mode": "off",
        "filename": "auto",
        "directory": "diag-output",
        "overflow_chars": 3500,
    }
    merged = {**defaults, **raw}
    mode = str(merged.get("mode", "off")).strip().lower()
    if mode not in _VALID_BUNDLE_MODES:
        mode = "off"
    merged["mode"] = mode
    return merged


def _overflow_threshold(config: Dict[str, Any], settings: Dict[str, Any]) -> int:
    guardrails = config.get("guardrails", {})
    reply = guardrails.get("reply", {}) if isinstance(guardrails, dict) else {}
    reply_max = int(reply.get("max_chars", 4000) or 4000)
    configured = int(settings.get("overflow_chars", 0) or 0)
    if configured > 0:
        return configured
    return max(1500, int(reply_max * 0.85))


def _combined_output_chars(
    actions: Sequence[MCPAction],
    execution_results: Sequence[str],
    blocked_commands: Sequence[str],
) -> int:
    total = sum(len(str(item)) for item in execution_results)
    total += sum(len(str(cmd)) for cmd in blocked_commands)
    total += sum(len(action.display_label()) for action in actions)
    return total


def should_bundle_outputs(
    *,
    config: Dict[str, Any],
    actions: Sequence[MCPAction],
    execution_results: Sequence[str],
    blocked_commands: Sequence[str],
) -> bool:
    if not execution_results and not blocked_commands:
        return False

    settings = bundle_settings(config)
    if settings["mode"] != "overflow_only":
        return False

    threshold = _overflow_threshold(config, settings)
    return _combined_output_chars(actions, execution_results, blocked_commands) > threshold


def resolve_bundle_filename(settings: Dict[str, Any], *, case_id: str = "") -> str:
    configured = str(settings.get("filename", "auto")).strip() or "auto"
    if configured.lower() != "auto":
        return configured
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_case = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (case_id or "case"))
    return f"diag-{safe_case}-{ts}.txt"


def build_bundle_content(
    *,
    case_id: str,
    actions: Sequence[MCPAction],
    execution_results: Sequence[str],
    blocked_commands: Sequence[str],
    policy: MCPPolicyChecker,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Agent diagnostic output bundle",
        f"# generated_at: {now}",
        f"# case_id: {case_id or 'unknown'}",
        "",
    ]

    if blocked_commands:
        lines.append("## Skipped commands (policy)")
        for cmd in blocked_commands:
            lines.append(explain_blocked_command(str(cmd), policy))
        lines.append("")

    for action, output in zip(actions, execution_results):
        label = action.label or action.display_label()
        lines.append(f"## {label}")
        lines.append(f"# tool: {action.tool}")
        argv = action.arguments.get("argv") or action.arguments.get("command")
        if isinstance(argv, list) and argv:
            lines.append("$ " + " ".join(str(part) for part in argv))
        lines.append(str(output or "(no output)"))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def resolve_bundle_path(config: Dict[str, Any], *, case_id: str = "") -> Path:
    settings = bundle_settings(config)
    directory = str(settings.get("directory", "diag-output")).strip() or "diag-output"
    filename = resolve_bundle_filename(settings, case_id=case_id)
    root = PROJECT_ROOT / directory
    root.mkdir(parents=True, exist_ok=True)
    return root / filename


def write_output_bundle(config: Dict[str, Any], content: str, *, case_id: str = "") -> Path:
    path = resolve_bundle_path(config, case_id=case_id)
    path.write_text(content, encoding="utf-8")
    return path


def build_upload_action(case_id: str, file_path: Path) -> MCPAction:
    return MCPAction(
        tool="upload_attachment_rh_portal",
        arguments={
            "case-number": case_id,
            "file": str(file_path),
        },
        label=f"upload {file_path.name}",
    )
