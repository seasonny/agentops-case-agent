"""Guardrailed ReAct investigate loop — Reason → Act → Observe within one poll cycle."""

from __future__ import annotations

from typing import Any, Dict, List

from core.logging import log_info, log_warning
from core.mcp_action import MCPAction
from core.mcp_policy import actions_from_payload


def investigation_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    inv = config.get("investigation") or {}
    return {
        "enabled": bool(inv.get("enabled", True)),
        "max_follow_up_steps": max(0, int(inv.get("max_follow_up_steps", 2))),
    }


def filter_follow_up_actions(
    raw_calls: Any,
    *,
    mcp_tool_names: List[str],
) -> List[MCPAction]:
    allowed = set(mcp_tool_names or [])
    actions = actions_from_payload(raw_calls)
    if not allowed:
        return actions
    filtered = [action for action in actions if action.tool in allowed]
    dropped = [action.tool for action in actions if action.tool not in allowed]
    if dropped:
        log_warning(
            "investigate_follow_up_dropped",
            tools=dropped,
            reason="tool_not_in_catalog",
        )
    return filtered


def should_continue_investigation(state: Dict[str, Any], config: Dict[str, Any]) -> bool:
    settings = investigation_settings(config)
    if not settings["enabled"]:
        return False
    if state.get("action_type") != "call_mcp":
        return False
    if state.get("approval_required"):
        return False
    if not state.get("needs_more_evidence"):
        return False
    follow_up = state.get("follow_up_mcp_actions") or []
    if not follow_up:
        log_info("investigate_skip", reason="no_follow_up_actions")
        return False
    step = int(state.get("investigate_step") or 0)
    if step >= settings["max_follow_up_steps"]:
        log_info(
            "investigate_max_steps",
            step=step,
            max_follow_up_steps=settings["max_follow_up_steps"],
        )
        return False
    return True


def serialize_actions(actions: List[MCPAction]) -> List[Dict[str, Any]]:
    return [
        {"tool": action.tool, "arguments": action.arguments, "label": action.label}
        for action in actions
    ]
