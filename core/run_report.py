"""Build structured run reports for SRE visibility."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.comments import parse_comment_timestamp
from core.poc_metrics import format_report_text, write_run_artifact


def _elapsed_seconds(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds(), 2)


def build_run_record(
    *,
    case_id: str,
    comment: Dict[str, Any],
    analysis,
    output: Dict[str, Any],
    dry_run: bool,
    started_at: datetime,
    finished_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    finished = finished_at or datetime.now(timezone.utc)
    se_ts = parse_comment_timestamp(comment)
    response_time: Optional[float] = None
    if se_ts:
        response_time = _elapsed_seconds(se_ts, finished)

    mcp_actions = output.get("all_mcp_actions") or output.get("mcp_actions") or []
    if not mcp_actions and analysis.mcp_calls:
        mcp_actions = [
            {"tool": a.tool, "arguments": a.arguments, "label": a.label}
            for a in analysis.mcp_calls
        ]

    tools = [str(a.get("tool", "")) for a in mcp_actions if isinstance(a, dict)]

    record: Dict[str, Any] = {
        "case_id": case_id,
        "comment_id": comment.get("id"),
        "comment_timestamp": comment.get("timestamp"),
        "author": comment.get("author"),
        "resolved_role": comment.get("resolved_role"),
        "trigger_reason": comment.get("_trigger_reason"),
        "request_preview": (comment.get("content") or "")[:200],
        "started_at": started_at.isoformat(),
        "finished_at": finished.isoformat(),
        "processing_duration_seconds": _elapsed_seconds(started_at, finished),
        "response_time_seconds": response_time,
        "dry_run": dry_run,
        "processing_completed": True,
        "action_type": output.get("action_type") or analysis.action_type,
        "intent": output.get("intent") or analysis.intent,
        "request_summary": output.get("request_summary") or analysis.summary,
        "analysis_source": output.get("analysis_source") or analysis.source,
        "analysis_prefilled": True,
        "mcp_tools": tools,
        "proposed_commands": output.get("proposed_commands") or analysis.commands,
        "policy_passed": output.get("policy_passed", True),
        "policy_reason": output.get("policy_reason", ""),
        "dangerous_command_blocked": bool(output.get("dangerous_command_blocked")),
        "dangerous_command_matched": output.get("dangerous_command_matched", ""),
        "blocked_commands": list(output.get("blocked_commands") or []),
        "execution_results": _truncate_results(output.get("execution_results") or []),
        "clarifying_questions": list(output.get("clarifying_questions") or []),
        "convergence_reason": output.get("convergence_reason", ""),
        "solution_summary": output.get("solution_summary", ""),
        "status_after_run": output.get("status", "POLLING"),
        "reply_posted": bool(output.get("reply_posted")),
        "composed_reply_preview": (output.get("composed_reply") or "")[:500],
        "diag_bundle_uploaded": bool(output.get("diag_bundle_uploaded")),
        "diag_bundle_filename": output.get("diag_bundle_filename", ""),
        "collection_uploaded": bool(output.get("collection_uploaded")),
        "collection_upload_filename": output.get("collection_upload_filename", ""),
        "attachment_verified": bool(output.get("attachment_verified")),
        "attachment_verify_detail": output.get("attachment_verify_detail", ""),
        "investigate_step": int(output.get("investigate_step") or 0),
        "needs_more_evidence": bool(output.get("needs_more_evidence")),
        "collaboration_source": output.get("collaboration_source", ""),
        "convergence_signal": output.get("convergence_signal", ""),
        "compose_skip_reason": output.get("compose_skip_reason", ""),
        "reply_skipped_reason": output.get("reply_skipped_reason", ""),
        "diagnosis_understanding": output.get("diagnosis_understanding", ""),
        "customer_actions": list(output.get("customer_actions") or []),
        "confirmation_questions": list(output.get("confirmation_questions") or []),
    }
    return record


def _truncate_results(results: List[Any], max_chars: int = 4000) -> List[str]:
    out: List[str] = []
    total = 0
    for item in results:
        text = str(item)
        if total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining > 0:
                out.append(text[:remaining] + "…(truncated)")
            break
        out.append(text)
        total += len(text)
    return out


def format_run_summary_human(record: Dict[str, Any]) -> str:
    """Single-run human-readable summary for SRE / dry-run review."""
    lines = [
        "Case Agent Run 摘要",
        "-" * 40,
        f"Case：{record.get('case_id')}",
        f"Comment #{record.get('comment_id')} · {record.get('author')} ({record.get('resolved_role')})",
        f"觸發原因：{record.get('trigger_reason') or '—'}",
        f"模式：{'dry-run（未發回覆）' if record.get('dry_run') else '正式執行'}",
        "",
        "請求摘要",
        f"  {record.get('request_summary') or record.get('request_preview') or '—'}",
        "",
        f"action_type：{record.get('action_type')}",
        f"intent：{record.get('intent')}",
    ]

    tools = record.get("mcp_tools") or []
    if tools:
        lines.extend(["", "MCP 工具", f"  {', '.join(tools)}"])

    commands = record.get("proposed_commands") or []
    if commands:
        lines.extend(["", "指令"])
        for cmd in commands[:10]:
            lines.append(f"  $ {cmd}")

    if not record.get("policy_passed", True):
        lines.extend(["", "Policy", f"  ❌ {record.get('policy_reason') or 'blocked'}"])
    elif record.get("blocked_commands"):
        lines.extend([
            "",
            "Policy",
            f"  ⚠ 略過危險指令：{', '.join(record['blocked_commands'])}",
        ])
    else:
        lines.extend(["", "Policy", "  ✅ 通過"])

    if record.get("dangerous_command_blocked"):
        lines.append(f"  危險指令攔截：{record.get('dangerous_command_matched')}")

    results = record.get("execution_results") or []
    if results:
        lines.extend(["", "執行結果（摘要）"])
        for i, result in enumerate(results[:5], 1):
            preview = str(result).replace("\n", " ")[:200]
            lines.append(f"  [{i}] {preview}")

    clarify = record.get("clarifying_questions") or []
    if clarify:
        lines.extend(["", "clarify 問題"])
        for q in clarify:
            lines.append(f"  ? {q}")

    reply = record.get("composed_reply_preview") or ""
    if reply:
        lines.extend(["", "將發回 / 已草擬回覆（前 500 字）", reply])

    collab_source = record.get("collaboration_source")
    if collab_source:
        lines.append(f"協作推理來源：{collab_source}")
    skip_reason = record.get("reply_skipped_reason") or record.get("compose_skip_reason")
    if skip_reason:
        lines.append(f"略過發回原因：{skip_reason}")

    lines.extend([
        "",
        f"回覆已發送：{'是' if record.get('reply_posted') else '否'}",
        f"處理耗時：{record.get('processing_duration_seconds')}s",
    ])
    if record.get("response_time_seconds") is not None:
        lines.append(f"SE 留言 → 完成本輪：{record.get('response_time_seconds')}s")

    return "\n".join(lines)


def persist_run_report(
    *,
    case_id: str,
    comment: Dict[str, Any],
    analysis,
    output: Dict[str, Any],
    dry_run: bool,
    started_at: datetime,
    finished_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    record = build_run_record(
        case_id=case_id,
        comment=comment,
        analysis=analysis,
        output=output,
        dry_run=dry_run,
        started_at=started_at,
        finished_at=finished_at,
    )
    write_run_artifact(case_id, record)
    return record
