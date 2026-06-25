"""PoC metrics persistence and summary for Case Agent runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import PROJECT_ROOT
from core.redaction import sanitize_for_storage

REPORTS_DIR = PROJECT_ROOT / "reports"


def metrics_path(case_id: str) -> Path:
    safe_id = case_id.strip() or "unknown"
    return REPORTS_DIR / safe_id / "metrics.json"


def runs_dir(case_id: str) -> Path:
    safe_id = case_id.strip() or "unknown"
    return REPORTS_DIR / safe_id / "runs"


def _empty_metrics(case_id: str) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "runs": [],
    }


def load_metrics(case_id: str) -> Dict[str, Any]:
    path = metrics_path(case_id)
    if not path.exists():
        return _empty_metrics(case_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return _empty_metrics(case_id)


def save_metrics(case_id: str, data: Dict[str, Any]) -> Path:
    path = metrics_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sanitize_for_storage(data), f, indent=2, ensure_ascii=False)
    return path


def append_run_record(case_id: str, record: Dict[str, Any]) -> Path:
    data = load_metrics(case_id)
    data["case_id"] = case_id
    runs: List[Dict[str, Any]] = data.setdefault("runs", [])
    runs.append(record)
    return save_metrics(case_id, data)


def summarize_metrics(case_id: str) -> Dict[str, Any]:
    data = load_metrics(case_id)
    runs = data.get("runs") or []
    if not runs:
        return {
            "case_id": case_id,
            "total_runs": 0,
            "message": "尚無 run 紀錄。請先執行 Agent 處理至少一則 Support 留言。",
        }

    completed = [r for r in runs if r.get("processing_completed")]
    replied = [r for r in runs if r.get("reply_posted")]
    dry_runs = [r for r in runs if r.get("dry_run")]
    clarifies = [r for r in runs if r.get("action_type") == "clarify"]
    blocked = [r for r in runs if not r.get("policy_passed", True) or r.get("dangerous_command_blocked")]
    response_times = [
        r["response_time_seconds"]
        for r in runs
        if isinstance(r.get("response_time_seconds"), (int, float))
    ]

    summary: Dict[str, Any] = {
        "case_id": case_id,
        "total_runs": len(runs),
        "completed_runs": len(completed),
        "replies_posted": len(replied),
        "dry_runs": len(dry_runs),
        "clarify_count": len(clarifies),
        "policy_blocked_count": len(blocked),
        "updated_at": data.get("updated_at"),
    }

    if response_times:
        summary["response_time_seconds"] = {
            "count": len(response_times),
            "min": round(min(response_times), 2),
            "max": round(max(response_times), 2),
            "avg": round(sum(response_times) / len(response_times), 2),
        }

    action_types: Dict[str, int] = {}
    for run in runs:
        at = str(run.get("action_type") or "unknown")
        action_types[at] = action_types.get(at, 0) + 1
    summary["action_type_counts"] = action_types

    return summary


def format_report_text(case_id: str, *, include_recent: int = 5) -> str:
    summary = summarize_metrics(case_id)
    data = load_metrics(case_id)
    runs = data.get("runs") or []

    lines = [
        f"Case Agent PoC 報告 — Case {case_id}",
        "=" * 48,
        "",
    ]

    if summary.get("total_runs", 0) == 0:
        lines.append(summary.get("message", "尚無資料。"))
        lines.append("")
        lines.append(f"metrics 檔案：{metrics_path(case_id)}")
        return "\n".join(lines)

    lines.extend([
        f"總 run 次數：{summary['total_runs']}",
        f"已完成處理：{summary['completed_runs']}",
        f"已發回覆：{summary['replies_posted']}",
        f"dry-run：{summary['dry_runs']}",
        f"clarify 次數：{summary['clarify_count']}",
        f"policy 阻擋次數：{summary['policy_blocked_count']}",
        "",
    ])

    rt = summary.get("response_time_seconds")
    if rt:
        lines.extend([
            "回應時效（秒，Agent 開始處理 → 完成本輪）",
            f"  樣本數：{rt['count']}",
            f"  平均：{rt['avg']}  最小：{rt['min']}  最大：{rt['max']}",
            "",
        ])

    counts = summary.get("action_type_counts") or {}
    if counts:
        lines.append("action_type 分布：")
        for key in sorted(counts):
            lines.append(f"  {key}: {counts[key]}")
        lines.append("")

    recent = runs[-include_recent:] if include_recent else runs
    if recent:
        lines.append(f"最近 {len(recent)} 次 run：")
        for run in recent:
            lines.append(_format_run_line(run))
        lines.append("")

    lines.append(f"metrics：{metrics_path(case_id)}")
    lines.append(f"run 報告目錄：{runs_dir(case_id)}")
    return "\n".join(lines)


def _format_run_line(run: Dict[str, Any]) -> str:
    ts = run.get("started_at", "?")[:19]
    action = run.get("action_type", "?")
    cid = run.get("comment_id", "?")
    dry = " [dry-run]" if run.get("dry_run") else ""
    posted = " → 已回覆" if run.get("reply_posted") else ""
    blocked = " [policy blocked]" if not run.get("policy_passed", True) else ""
    rt = run.get("response_time_seconds")
    rt_str = f" {rt}s" if isinstance(rt, (int, float)) else ""
    preview = (run.get("request_preview") or "")[:60]
    return f"  - {ts} comment#{cid} {action}{dry}{blocked}{posted}{rt_str} | {preview}"


def write_run_artifact(case_id: str, record: Dict[str, Any]) -> Path:
    """Write individual run JSON and append to aggregate metrics."""
    run_dir = runs_dir(case_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    started = record.get("started_at") or datetime.now(timezone.utc).isoformat()
    safe_ts = started.replace(":", "-").replace("+", "_")
    path = run_dir / f"run-{safe_ts}.json"
    safe_record = sanitize_for_storage(record)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe_record, f, indent=2, ensure_ascii=False)
    append_run_record(case_id, safe_record)
    return path
