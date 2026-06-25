"""Human-in-the-loop approval for high-risk MCP actions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from core.config import PROJECT_ROOT
from core.enterprise import approval_enabled, approval_required_tools
from core.mcp_action import MCPAction
from core.redaction import sanitize_for_storage

APPROVAL_ROOT = PROJECT_ROOT / "reports"


def approvals_path(case_id: str) -> Path:
    safe = (case_id or "unknown").strip() or "unknown"
    return APPROVAL_ROOT / safe / "approvals.json"


def _empty_store() -> Dict[str, Any]:
    return {"approved": [], "pending": []}


def load_approvals(case_id: str) -> Dict[str, Any]:
    path = approvals_path(case_id)
    if not path.exists():
        return _empty_store()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("approved", [])
            data.setdefault("pending", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return _empty_store()


def save_approvals(case_id: str, data: Dict[str, Any]) -> Path:
    path = approvals_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(sanitize_for_storage(data), handle, indent=2, ensure_ascii=False)
    return path


def action_fingerprint(action: MCPAction) -> str:
    payload = json.dumps(
        {"tool": action.tool, "arguments": action.arguments},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def requires_approval(action: MCPAction, config: Dict[str, Any]) -> bool:
    if not approval_enabled(config):
        return False
    return action.tool in set(approval_required_tools(config))


def filter_unapproved_actions(
    case_id: str,
    actions: Sequence[MCPAction],
    config: Dict[str, Any],
) -> List[MCPAction]:
    pending: List[MCPAction] = []
    for action in actions:
        if not requires_approval(action, config):
            continue
        if not is_action_approved(case_id, action):
            pending.append(action)
    return pending


def is_action_approved(case_id: str, action: MCPAction) -> bool:
    fp = action_fingerprint(action)
    store = load_approvals(case_id)
    for item in store.get("approved", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("fingerprint", "")) == fp:
            return True
        if item.get("tool") == action.tool and item.get("arguments") == action.arguments:
            return True
    return False


def register_pending_approvals(
    case_id: str,
    actions: Sequence[MCPAction],
    *,
    comment_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    created: List[Dict[str, Any]] = []
    existing_fps = {
        str(item.get("fingerprint", ""))
        for item in pending + list(store.get("approved", []))
        if isinstance(item, dict)
    }

    for action in actions:
        fp = action_fingerprint(action)
        if fp in existing_fps:
            continue
        entry = {
            "fingerprint": fp,
            "tool": action.tool,
            "arguments": action.arguments,
            "label": action.label or action.display_label(),
            "comment_id": comment_id,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        pending.append(entry)
        created.append(entry)
        existing_fps.add(fp)

    store["pending"] = pending
    save_approvals(case_id, store)
    return created


def approve_fingerprint(
    case_id: str,
    fingerprint: str,
    *,
    approved_by: str = "",
) -> bool:
    fp = fingerprint.strip().lower()
    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    approved = list(store.get("approved", []))

    matched = None
    remaining = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        if str(item.get("fingerprint", "")).lower() == fp:
            matched = dict(item)
        else:
            remaining.append(item)

    if matched is None:
        for item in pending:
            if isinstance(item, dict):
                remaining.append(item)
        for item in approved:
            if isinstance(item, dict) and str(item.get("fingerprint", "")).lower() == fp:
                return True
        return False

    matched["approved_at"] = datetime.now(timezone.utc).isoformat()
    matched["approved_by"] = approved_by or "operator"
    approved.append(matched)
    store["pending"] = remaining
    store["approved"] = approved
    save_approvals(case_id, store)
    return True


def format_pending_approvals_text(case_id: str) -> str:
    store = load_approvals(case_id)
    pending = store.get("pending", [])
    if not pending:
        return f"Case {case_id}：無待核准項目。"

    lines = [f"Case {case_id} — 待核准 MCP 操作", "-" * 40]
    for item in pending:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"  {item.get('fingerprint')}  {item.get('tool')}  {item.get('label', '')}"
        )
    lines.append("")
    lines.append(f"核准：python main.py --approve {case_id} <fingerprint> --approved-by <name>")
    lines.append(f"檔案：{approvals_path(case_id)}")
    return "\n".join(lines)


def format_approval_required_reply(pending: Sequence[Dict[str, Any]]) -> str:
    lines = ["以下操作需人工核准後才會執行："]
    for item in pending:
        fp = item.get("fingerprint", "?")
        label = item.get("label") or item.get("tool", "?")
        lines.append(f"- [{fp}] {label}")
    lines.append("")
    lines.append("核准後 Agent 會在下一輪輪詢自動重試。")
    return "\n".join(lines)
