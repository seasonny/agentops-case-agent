"""Case-level diagnostics and collaboration memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from core.enterprise import diagnostics_history_limit, diagnostics_tracking_enabled
from core.mcp_action import MCPAction


def record_diagnostics(
    memory: Dict[str, Any],
    actions: Sequence[MCPAction],
    *,
    comment_id: int,
    config: Dict[str, Any],
    execution_results: Optional[Sequence[str]] = None,
) -> None:
    if not diagnostics_tracking_enabled(config):
        return
    if not actions:
        return

    history: List[Dict[str, Any]] = list(memory.get("diagnostics_history", []))
    now = datetime.now(timezone.utc).isoformat()
    limit = diagnostics_history_limit(config)

    for action, result in zip(actions, execution_results or []):
        preview = str(result or "")[:200]
        history.append({
            "at": now,
            "comment_id": comment_id,
            "tool": action.tool,
            "label": action.label or action.display_label(),
            "arguments": action.arguments,
            "result_preview": preview,
        })

    memory["diagnostics_history"] = history[-limit:]


def format_diagnostics_context(memory: Dict[str, Any], *, max_items: int = 8) -> str:
    history = memory.get("diagnostics_history") or []
    if not history:
        return ""

    lines = ["Previously executed diagnostics (do not repeat unless Support asks):"]
    for item in history[-max_items:]:
        if not isinstance(item, dict):
            continue
        label = item.get("label") or item.get("tool", "?")
        cid = item.get("comment_id", "?")
        lines.append(f"- [{item.get('at', '?')[:19]}] comment#{cid}: {label}")
    return "\n".join(lines)


def record_hypothesis(
    memory: Dict[str, Any],
    *,
    comment_id: int,
    request_summary: str,
    diagnosis_understanding: str = "",
    customer_actions: Optional[List[str]] = None,
    confirmation_questions: Optional[List[str]] = None,
    verification_plan: str = "",
    convergence_signal: str = "none",
    customer_voice: str = "",
) -> None:
    """Track Support diagnosis and customer response for continuity across turns."""
    understanding = (diagnosis_understanding or "").strip()
    actions = [str(a).strip() for a in (customer_actions or []) if str(a).strip()]
    questions = [str(q).strip() for q in (confirmation_questions or []) if str(q).strip()]
    if not any([understanding, actions, questions, verification_plan, customer_voice]):
        return

    history: List[Dict[str, Any]] = list(memory.get("hypothesis_tracker", []))
    now = datetime.now(timezone.utc).isoformat()
    history.append({
        "at": now,
        "comment_id": comment_id,
        "support_summary": (request_summary or "")[:500],
        "diagnosis_understanding": understanding,
        "customer_actions": actions,
        "confirmation_questions": questions,
        "verification_plan": (verification_plan or "").strip(),
        "convergence_signal": (convergence_signal or "none").strip(),
        "customer_voice_preview": (customer_voice or "")[:300],
    })
    memory["hypothesis_tracker"] = history[-12:]


def format_hypothesis_context(memory: Dict[str, Any], *, max_items: int = 5) -> str:
    history = memory.get("hypothesis_tracker") or []
    if not history:
        return "(none)"

    lines = ["Prior collaboration hypotheses (build on these, do not repeat hollow acks):"]
    for item in history[-max_items:]:
        if not isinstance(item, dict):
            continue
        cid = item.get("comment_id", "?")
        signal = item.get("convergence_signal", "none")
        understanding = item.get("diagnosis_understanding", "")
        actions = item.get("customer_actions") or []
        questions = item.get("confirmation_questions") or []
        parts = [f"- comment#{cid} [{signal}]"]
        if understanding:
            parts.append(f"  understood: {understanding}")
        if actions:
            parts.append(f"  actions: {'; '.join(actions)}")
        if questions:
            parts.append(f"  open questions: {'; '.join(questions)}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


def augment_case_history(case_history: str, memory: Dict[str, Any]) -> str:
    sections = [case_history]
    diag = format_diagnostics_context(memory)
    if diag:
        sections.append(diag)
    hypothesis = format_hypothesis_context(memory)
    if hypothesis and hypothesis != "(none)":
        sections.append(hypothesis)
    return "\n\n---\n\n".join(sections)
