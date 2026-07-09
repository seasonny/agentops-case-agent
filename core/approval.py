"""Human-in-the-loop approval for high-risk MCP actions."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.config import PROJECT_ROOT
from core.enterprise import (
    approval_enabled,
    approval_required_tools,
    approval_ttl_hours,
    connector_reply_mode,
)
from core.mcp_action import MCPAction
from core.redaction import sanitize_for_storage

APPROVAL_ROOT = PROJECT_ROOT / "reports"

RESUME_PENDING = "pending_resume"
RESUME_DONE = "resumed"
RESUME_EXPIRED = "expired"
RESUME_DENIED = "denied"


def approvals_path(case_id: str) -> Path:
    safe = (case_id or "unknown").strip() or "unknown"
    return APPROVAL_ROOT / safe / "approvals.json"


def _empty_store() -> Dict[str, Any]:
    return {"approved": [], "pending": [], "denied": []}


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
            data.setdefault("denied", [])
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


def build_correlation_id(
    case_id: str,
    comment_id: Optional[int],
    fingerprint: str,
) -> str:
    cid = comment_id if comment_id is not None else 0
    return f"{case_id}:{cid}:{fingerprint}"


def _new_pending_id() -> str:
    return f"pend-{uuid.uuid4().hex[:12]}"


def _expires_at_iso(config: Dict[str, Any]) -> str:
    hours = approval_ttl_hours(config)
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _parse_iso(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


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
    """One-shot grants: historical approvals do not waive future requests."""
    _ = (case_id, action)
    return False


def actions_covered_by_resume_grant(
    case_id: str,
    pending_id: str,
    actions: Sequence[MCPAction],
) -> bool:
    """True when actions match a granted pending_resume entry for this resume."""
    pid = (pending_id or "").strip()
    if not pid or not actions:
        return False

    for item in list_resumable_approved(case_id):
        if str(item.get("pending_id", "")) != pid:
            continue
        ctx = item.get("workflow_context") or {}
        granted_raw = ctx.get("mcp_actions") or []
        granted_fps: set[str] = set()
        for raw in granted_raw:
            if not isinstance(raw, dict) or not raw.get("tool"):
                continue
            granted_fps.add(
                action_fingerprint(
                    MCPAction(
                        tool=str(raw.get("tool", "")),
                        arguments=dict(raw.get("arguments") or {}),
                        label=str(raw.get("label", "")),
                    )
                )
            )
        if not granted_fps:
            return False
        action_fps = {action_fingerprint(action) for action in actions}
        return action_fps == granted_fps
    return False


def register_pending_approvals(
    case_id: str,
    actions: Sequence[MCPAction],
    *,
    comment_id: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    created: List[Dict[str, Any]] = []
    existing_fps = {
        str(item.get("fingerprint", ""))
        for item in pending
        if isinstance(item, dict) and item.get("fingerprint")
    }
    resumable_fps = _resumable_fingerprints(case_id)
    cfg = config or {}
    expires_at = _expires_at_iso(cfg) if cfg else None

    for action in actions:
        fp = action_fingerprint(action)
        if fp in existing_fps:
            for item in pending:
                if isinstance(item, dict) and str(item.get("fingerprint", "")) == fp:
                    created.append(dict(item))
                    break
            continue
        if fp in resumable_fps:
            for item in list_resumable_approved(case_id):
                if str(item.get("fingerprint", "")) == fp:
                    created.append(dict(item))
                    break
            continue
        entry = {
            "pending_id": _new_pending_id(),
            "workflow_id": None,
            "fingerprint": fp,
            "tool": action.tool,
            "arguments": action.arguments,
            "label": action.label or action.display_label(),
            "comment_id": comment_id,
            "correlation_id": build_correlation_id(case_id, comment_id, fp),
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,
            "resume_status": None,
        }
        entry["workflow_id"] = entry["pending_id"]
        pending.append(entry)
        created.append(entry)
        existing_fps.add(fp)

    store["pending"] = pending
    save_approvals(case_id, store)
    return created


def persist_workflow_context(
    case_id: str,
    *,
    fingerprints: Sequence[str],
    workflow_context: Dict[str, Any],
) -> None:
    """Attach resume snapshot to pending entries after approval workflow."""
    if not fingerprints:
        return
    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    fps = {str(fp) for fp in fingerprints}
    updated = False
    for item in pending:
        if not isinstance(item, dict):
            continue
        if str(item.get("fingerprint", "")) not in fps:
            continue
        item["workflow_context"] = dict(workflow_context)
        updated = True
    if updated:
        store["pending"] = pending
        save_approvals(case_id, store)


def _workflow_context_snapshot(
    memory: Dict[str, Any],
    *,
    comment: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "comment_id": comment.get("id"),
        "latest_msg": memory.get("latest_msg", comment.get("content", "")),
        "action_type": "call_mcp",
        "mcp_actions": list(memory.get("mcp_actions") or []),
        "request_summary": memory.get("request_summary", ""),
        "blocked_commands": list(memory.get("blocked_commands") or []),
        "intent": memory.get("intent", ""),
        "analysis_source": memory.get("analysis_source", ""),
        "proposed_commands": list(memory.get("proposed_commands") or []),
        "clarifying_questions": list(memory.get("clarifying_questions") or []),
    }


def persist_workflow_context_from_memory(
    case_id: str,
    *,
    memory: Dict[str, Any],
    comment: Dict[str, Any],
    pending: Sequence[Dict[str, Any]],
) -> None:
    fingerprints = [
        str(item.get("fingerprint", ""))
        for item in pending
        if isinstance(item, dict) and item.get("fingerprint")
    ]
    persist_workflow_context(
        case_id,
        fingerprints=fingerprints,
        workflow_context=_workflow_context_snapshot(memory, comment=comment),
    )


def _resumable_fingerprints(case_id: str) -> set[str]:
    return {
        str(item.get("fingerprint", ""))
        for item in list_resumable_approved(case_id)
        if item.get("fingerprint")
    }


def _supersede_duplicate_resumable(
    approved: List[Dict[str, Any]],
    *,
    correlation_id: str,
    keep_pending_id: str,
) -> None:
    """Mark older grants for the same plan as resumed so poll does not replay them."""
    if not correlation_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    for item in approved:
        if not isinstance(item, dict):
            continue
        if str(item.get("correlation_id", "")) != correlation_id:
            continue
        if str(item.get("pending_id", "")) == keep_pending_id:
            continue
        if item.get("resume_status") != RESUME_PENDING:
            continue
        item["resume_status"] = RESUME_DONE
        item["resumed_at"] = now
        item["superseded_by"] = keep_pending_id


def _remove_related_pending(
    pending: Sequence[Dict[str, Any]],
    matched: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Remove pending items for the same plan (correlation_id or fingerprint)."""
    correlation_id = str(matched.get("correlation_id", ""))
    fingerprint = str(matched.get("fingerprint", "")).lower()
    remaining: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        same_plan = False
        if correlation_id and str(item.get("correlation_id", "")) == correlation_id:
            same_plan = True
        elif fingerprint and str(item.get("fingerprint", "")).lower() == fingerprint:
            same_plan = True
        if same_plan:
            removed.append(dict(item))
        else:
            remaining.append(item)
    if not removed:
        removed.append(dict(matched))
        remaining = [
            item
            for item in remaining
            if str(item.get("pending_id", "")) != str(matched.get("pending_id", ""))
        ]
    return remaining, removed


def _cancel_resumable_grants_for_plan(
    approved: List[Dict[str, Any]],
    *,
    correlation_id: str,
    denied_pending_id: str,
    denied_by: str,
    deny_reason: str,
) -> None:
    """Mark waiting grants for the same plan as denied so poll will not resume them."""
    if not correlation_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    for item in approved:
        if not isinstance(item, dict):
            continue
        if str(item.get("correlation_id", "")) != correlation_id:
            continue
        if item.get("resume_status") != RESUME_PENDING:
            continue
        item["resume_status"] = RESUME_DENIED
        item["denied_at"] = now
        item["denied_by"] = denied_by
        item["denied_via"] = "superseded_by_deny"
        item["deny_reason"] = deny_reason or "superseded by deny"
        item["superseded_by"] = denied_pending_id


def _match_pending_item(pending: Sequence[Dict[str, Any]], token: str) -> Optional[Dict[str, Any]]:
    needle = token.strip()
    if not needle:
        return None
    lowered = needle.lower()
    for item in pending:
        if not isinstance(item, dict):
            continue
        if str(item.get("pending_id", "")) == needle:
            return dict(item)
        if str(item.get("fingerprint", "")).lower() == lowered:
            return dict(item)
    return None


def approve_token(
    case_id: str,
    token: str,
    *,
    approved_by: str = "",
    approved_via: str = "cli:operator",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Approve by fingerprint or pending_id (pend-...)."""
    needle = (token or "").strip()
    if not needle:
        return False, None

    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    approved = list(store.get("approved", []))

    matched = _match_pending_item(pending, needle)
    remaining = []
    if matched is not None:
        for item in pending:
            if not isinstance(item, dict):
                continue
            if str(item.get("pending_id", "")) == matched.get("pending_id"):
                continue
            if (
                str(item.get("fingerprint", "")).lower()
                == str(matched.get("fingerprint", "")).lower()
            ):
                continue
            remaining.append(item)
    else:
        remaining = [item for item in pending if isinstance(item, dict)]
        for item in approved:
            if not isinstance(item, dict):
                continue
            if needle.lower().startswith("pend-"):
                if str(item.get("pending_id", "")) != needle:
                    continue
            elif str(item.get("fingerprint", "")).lower() != needle.lower():
                continue
            if item.get("resume_status") == RESUME_PENDING:
                return True, dict(item)
        return False, None

    matched["approved_at"] = datetime.now(timezone.utc).isoformat()
    matched["approved_by"] = approved_by or "operator"
    matched["approved_via"] = approved_via
    matched["resume_status"] = RESUME_PENDING
    _supersede_duplicate_resumable(
        approved,
        correlation_id=str(matched.get("correlation_id", "")),
        keep_pending_id=str(matched.get("pending_id", "")),
    )
    approved.append(matched)
    store["pending"] = remaining
    store["approved"] = approved
    save_approvals(case_id, store)
    return True, matched


def approve_fingerprint(
    case_id: str,
    fingerprint: str,
    *,
    approved_by: str = "",
    approved_via: str = "cli:operator",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Backward-compatible alias for approve_token."""
    return approve_token(
        case_id,
        fingerprint,
        approved_by=approved_by,
        approved_via=approved_via,
    )


def approve_latest(
    case_id: str,
    *,
    approved_by: str = "",
    approved_via: str = "cli:operator",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Approve the oldest pending item for the case."""
    store = load_approvals(case_id)
    pending = [item for item in store.get("pending", []) if isinstance(item, dict)]
    if not pending:
        return False, None
    oldest = sorted(pending, key=lambda item: str(item.get("requested_at", "")))[0]
    token = str(oldest.get("pending_id") or oldest.get("fingerprint", ""))
    return approve_token(
        case_id,
        token,
        approved_by=approved_by,
        approved_via=approved_via,
    )


def _match_resumable_grant(
    approved: Sequence[Dict[str, Any]],
    token: str,
) -> Optional[Dict[str, Any]]:
    needle = token.strip()
    if not needle:
        return None
    lowered = needle.lower()
    for item in approved:
        if not isinstance(item, dict):
            continue
        if item.get("resume_status") != RESUME_PENDING:
            continue
        if str(item.get("pending_id", "")) == needle:
            return dict(item)
        if str(item.get("fingerprint", "")).lower() == lowered:
            return dict(item)
    return None


def deny_token(
    case_id: str,
    token: str,
    *,
    denied_by: str = "",
    denied_via: str = "cli:operator",
    reason: str = "",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Explicitly deny a pending MCP plan (will not execute)."""
    needle = (token or "").strip()
    if not needle:
        return False, None

    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    approved = list(store.get("approved", []))
    denied = list(store.get("denied", []))

    matched = _match_pending_item(pending, needle)
    if matched is None:
        grant = _match_resumable_grant(approved, needle)
        if grant is None:
            return False, None
        now = datetime.now(timezone.utc).isoformat()
        denied_entry = dict(grant)
        denied_entry["denied_at"] = now
        denied_entry["denied_by"] = denied_by or "operator"
        denied_entry["denied_via"] = denied_via
        denied_entry["deny_reason"] = (reason or "").strip()
        denied_entry["resume_status"] = RESUME_DENIED
        for item in approved:
            if not isinstance(item, dict):
                continue
            if str(item.get("pending_id", "")) != str(grant.get("pending_id", "")):
                continue
            item.update(
                {
                    "denied_at": now,
                    "denied_by": denied_entry["denied_by"],
                    "denied_via": denied_via,
                    "deny_reason": denied_entry["deny_reason"],
                    "resume_status": RESUME_DENIED,
                }
            )
        _cancel_resumable_grants_for_plan(
            approved,
            correlation_id=str(grant.get("correlation_id", "")),
            denied_pending_id=str(grant.get("pending_id", "")),
            denied_by=denied_entry["denied_by"],
            deny_reason=denied_entry["deny_reason"],
        )
        remaining, _removed = _remove_related_pending(pending, grant)
        denied.append(denied_entry)
        store["pending"] = remaining
        store["approved"] = approved
        store["denied"] = denied
        save_approvals(case_id, store)
        return True, denied_entry

    remaining, _removed = _remove_related_pending(pending, matched)
    now = datetime.now(timezone.utc).isoformat()
    denied_entry = dict(matched)
    denied_entry["denied_at"] = now
    denied_entry["denied_by"] = denied_by or "operator"
    denied_entry["denied_via"] = denied_via
    denied_entry["deny_reason"] = (reason or "").strip()
    denied_entry["resume_status"] = RESUME_DENIED
    _cancel_resumable_grants_for_plan(
        approved,
        correlation_id=str(matched.get("correlation_id", "")),
        denied_pending_id=str(matched.get("pending_id", "")),
        denied_by=denied_entry["denied_by"],
        deny_reason=denied_entry["deny_reason"],
    )
    denied.append(denied_entry)
    store["pending"] = remaining
    store["approved"] = approved
    store["denied"] = denied
    save_approvals(case_id, store)
    return True, denied_entry


def deny_latest(
    case_id: str,
    *,
    denied_by: str = "",
    denied_via: str = "cli:operator",
    reason: str = "",
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Deny the oldest pending item for the case."""
    store = load_approvals(case_id)
    pending = [item for item in store.get("pending", []) if isinstance(item, dict)]
    if not pending:
        return False, None
    oldest = sorted(pending, key=lambda item: str(item.get("requested_at", "")))[0]
    token = str(oldest.get("pending_id") or oldest.get("fingerprint", ""))
    return deny_token(
        case_id,
        token,
        denied_by=denied_by,
        denied_via=denied_via,
        reason=reason,
    )


def mark_pending_resumed(case_id: str, pending_id: str) -> bool:
    pid = (pending_id or "").strip()
    if not pid:
        return False
    store = load_approvals(case_id)
    approved = list(store.get("approved", []))
    found = False
    correlation_id = ""
    now = datetime.now(timezone.utc).isoformat()
    for item in approved:
        if not isinstance(item, dict):
            continue
        if str(item.get("pending_id", "")) == pid:
            correlation_id = str(item.get("correlation_id", ""))
            item["resume_status"] = RESUME_DONE
            item["resumed_at"] = now
            found = True
            break
    if not found:
        return False
    if correlation_id:
        _supersede_duplicate_resumable(
            approved,
            correlation_id=correlation_id,
            keep_pending_id=pid,
        )
    store["approved"] = approved
    save_approvals(case_id, store)
    return True


def list_resumable_approved(case_id: str) -> List[Dict[str, Any]]:
    store = load_approvals(case_id)
    resumable: List[Dict[str, Any]] = []
    for item in store.get("approved", []):
        if not isinstance(item, dict):
            continue
        if item.get("resume_status") != RESUME_PENDING:
            continue
        if not item.get("workflow_context"):
            continue
        expires = _parse_iso(item.get("expires_at"))
        if expires and datetime.now(timezone.utc) > expires:
            continue
        resumable.append(dict(item))
    resumable.sort(key=lambda x: str(x.get("approved_at", "")))
    return _dedupe_resumable_by_correlation(resumable)


def _dedupe_resumable_by_correlation(
    items: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """One resume per correlation_id — keep the oldest grant."""
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for item in items:
        key = str(item.get("correlation_id", "")) or str(item.get("pending_id", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def expire_stale_pending(case_id: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Move expired pending items out of the active queue."""
    _ = config  # reserved for per-rule TTL overrides
    store = load_approvals(case_id)
    pending = list(store.get("pending", []))
    approved = list(store.get("approved", []))
    now = datetime.now(timezone.utc)
    kept: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []
    for item in pending:
        if not isinstance(item, dict):
            continue
        expires = _parse_iso(item.get("expires_at"))
        if expires and now > expires:
            expired_item = dict(item)
            expired_item["resume_status"] = RESUME_EXPIRED
            expired_item["expired_at"] = now.isoformat()
            expired.append(expired_item)
            approved.append(expired_item)
        else:
            kept.append(item)

    new_approved: List[Dict[str, Any]] = []
    for item in approved:
        if not isinstance(item, dict):
            new_approved.append(item)
            continue
        if item.get("resume_status") == RESUME_PENDING:
            expires = _parse_iso(item.get("expires_at"))
            if expires and now > expires:
                expired_item = dict(item)
                expired_item["resume_status"] = RESUME_EXPIRED
                expired_item["expired_at"] = now.isoformat()
                expired.append(expired_item)
                new_approved.append(expired_item)
                continue
        new_approved.append(item)

    if expired:
        store["pending"] = kept
        store["approved"] = new_approved
        save_approvals(case_id, store)
    return expired


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
        if item.get("pending_id"):
            lines.append(f"    pending_id: {item.get('pending_id')}")
    lines.append("")
    lines.append("核准為一次一批：每筆待執行計畫需單獨 approve，執行後須重新核准。")
    lines.append(f"核准（最新一筆）：python3 main.py --case-id={case_id} --approve-latest --approved-by <name>")
    lines.append(
        f"核准（指定）：python3 main.py --case-id={case_id} "
        f"--approve <fingerprint|pending_id> --approved-by <name>"
    )
    lines.append(f"拒絕（最新一筆）：python3 main.py --case-id={case_id} --deny-latest --denied-by <name> --deny-reason \"<原因>\"")
    lines.append(
        f"拒絕（指定）：python3 main.py --case-id={case_id} "
        f"--deny <fingerprint|pending_id> --denied-by <name> --deny-reason \"<原因>\""
    )
    lines.append(f"或：make approve CASE_ID={case_id} BY=<name>  /  make deny CASE_ID={case_id} BY=<name> REASON=\"<原因>\"")
    lines.append(f"檔案：{approvals_path(case_id)}")
    return "\n".join(lines)


def format_approval_required_reply(
    pending: Sequence[Dict[str, Any]],
    *,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    mode = connector_reply_mode(config or {})
    items = [item for item in pending if isinstance(item, dict)]
    if mode == "silent":
        return "所請求的操作需經內部核准，完成後將另行回報。"

    if mode == "customer_status":
        lines = ["以下操作需經內部核准後才會執行："]
        for item in items:
            label = item.get("label") or item.get("tool", "?")
            lines.append(f"- {label}")
        lines.append("")
        lines.append("核准完成後 Agent 將自動接續執行並回報結果。")
        return "\n".join(lines)

    lines = ["以下操作需人工核准後才會執行："]
    for item in items:
        fp = item.get("fingerprint", "?")
        label = item.get("label") or item.get("tool", "?")
        lines.append(f"- [{fp}] {label}")
    lines.append("")
    lines.append("核准完成後 Agent 將自動接續執行（不需新 trigger 留言）。")
    return "\n".join(lines)


def format_approval_pending_for_compose(
    pending: Optional[Sequence[Dict[str, Any]]],
    *,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    items = [item for item in (pending or []) if isinstance(item, dict)]
    if not items:
        return "(none)"
    mode = connector_reply_mode(config or {})
    if mode == "customer_status":
        return format_approval_required_reply(items, config=config)
    if mode == "silent":
        return "(internal approval required — do not expose fingerprints to customer)"
    lines = []
    for item in items:
        fp = item.get("fingerprint", "?")
        label = item.get("label") or item.get("tool", "?")
        lines.append(f"- [{fp}] {label}")
    return "\n".join(lines)
