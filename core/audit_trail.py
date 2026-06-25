"""Persistent audit trail for Enterprise compliance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import PROJECT_ROOT
from core.enterprise import audit_trail_enabled, tenant_id, tenant_label
from core.redaction import sanitize_for_log

AUDIT_ROOT = PROJECT_ROOT / "reports"


def audit_path(case_id: str) -> Path:
    safe = (case_id or "unknown").strip() or "unknown"
    return AUDIT_ROOT / safe / "audit.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit_record(case_id: str, record: Dict[str, Any]) -> None:
    path = audit_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = sanitize_for_log(dict(record))
    payload.setdefault("ts", _now_iso())
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class AuditTrail:
    """Context-bound audit writer for a single poll/workflow run."""

    def __init__(
        self,
        *,
        config: Dict[str, Any],
        case_id: str,
        enabled: Optional[bool] = None,
    ):
        self.config = config
        self.case_id = case_id
        self.enabled = audit_trail_enabled(config) if enabled is None else enabled

    def _base(self, **fields: Any) -> Dict[str, Any]:
        base = {
            "case_id": self.case_id,
            "tenant_id": tenant_id(self.config) or None,
            "tenant_label": tenant_label(self.config) or None,
        }
        base.update(fields)
        return base

    def record(
        self,
        event: str,
        *,
        comment_id: Optional[int] = None,
        dry_run: bool = False,
        **fields: Any,
    ) -> None:
        if not self.enabled:
            return
        append_audit_record(
            self.case_id,
            self._base(event=event, comment_id=comment_id, dry_run=dry_run, **fields),
        )

    def record_policy(
        self,
        *,
        comment_id: Optional[int],
        passed: bool,
        reason: str,
        tools: List[str],
        dry_run: bool = False,
    ) -> None:
        self.record(
            "policy_check",
            comment_id=comment_id,
            dry_run=dry_run,
            policy_passed=passed,
            policy_reason=reason,
            tools=tools,
        )

    def record_mcp_call(
        self,
        action: Any,
        *,
        comment_id: Optional[int],
        provider: str,
        actual_tool: str,
        result_preview: str,
        dry_run: bool = False,
    ) -> None:
        self.record(
            "mcp_call",
            comment_id=comment_id,
            dry_run=dry_run,
            tool=action.tool,
            actual_tool=actual_tool,
            provider=provider,
            arguments=action.arguments,
            label=action.label,
            result_preview=(result_preview or "")[:500],
        )

    def record_reply(
        self,
        *,
        comment_id: Optional[int],
        posted: bool,
        action_type: str,
        dry_run: bool = False,
    ) -> None:
        self.record(
            "case_reply",
            comment_id=comment_id,
            dry_run=dry_run,
            reply_posted=posted,
            action_type=action_type,
        )


def load_audit_records(case_id: str, *, limit: int = 200) -> List[Dict[str, Any]]:
    path = audit_path(case_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
        except json.JSONDecodeError:
            continue
    return records


def summarize_audit(case_id: str) -> Dict[str, Any]:
    records = load_audit_records(case_id, limit=5000)
    if not records:
        return {
            "case_id": case_id,
            "total_events": 0,
            "message": "尚無 audit 紀錄",
        }

    by_event: Dict[str, int] = {}
    mcp_calls = 0
    policy_blocks = 0
    for rec in records:
        event = str(rec.get("event", "unknown"))
        by_event[event] = by_event.get(event, 0) + 1
        if event == "mcp_call":
            mcp_calls += 1
        if event == "policy_check" and rec.get("policy_passed") is False:
            policy_blocks += 1

    return {
        "case_id": case_id,
        "total_events": len(records),
        "event_counts": by_event,
        "mcp_calls": mcp_calls,
        "policy_blocks": policy_blocks,
        "first_ts": records[0].get("ts"),
        "last_ts": records[-1].get("ts"),
        "audit_path": str(audit_path(case_id)),
    }


def format_audit_report_text(case_id: str) -> str:
    summary = summarize_audit(case_id)
    lines = [
        f"Audit Trail — Case {case_id}",
        "=" * 48,
        f"總事件數：{summary.get('total_events', 0)}",
    ]
    if summary.get("total_events", 0) == 0:
        lines.append(summary.get("message", ""))
        lines.append(f"\n檔案：{audit_path(case_id)}")
        return "\n".join(lines)

    lines.extend([
        f"MCP 呼叫：{summary.get('mcp_calls', 0)}",
        f"Policy 阻擋：{summary.get('policy_blocks', 0)}",
        f"時間範圍：{summary.get('first_ts')} → {summary.get('last_ts')}",
        "",
        "事件分布：",
    ])
    for key in sorted(summary.get("event_counts", {})):
        lines.append(f"  {key}: {summary['event_counts'][key]}")

    recent = load_audit_records(case_id, limit=10)
    if recent:
        lines.extend(["", "最近 10 筆："])
        for rec in recent:
            ts = str(rec.get("ts", ""))[:19]
            event = rec.get("event", "?")
            tool = rec.get("tool") or rec.get("action_type") or ""
            extra = f" tool={tool}" if tool else ""
            lines.append(f"  - {ts} {event}{extra}")

    lines.append(f"\n檔案：{audit_path(case_id)}")
    return "\n".join(lines)
