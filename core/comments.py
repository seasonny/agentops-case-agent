import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent_settings import get_reply_prefix
from core.constants import (
    AGENT_REPLY_PREFIX,
    TURN_COOLDOWN,
    TURN_WAITING,
)
from core.logging import log_info


def parse_rh_portal_comments(raw_text: Any) -> List[Dict[str, Any]]:
    if not raw_text:
        return []

    if isinstance(raw_text, list):
        text_parts: List[str] = []
        for item in raw_text:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
                else:
                    text_parts.append(str(item))
            else:
                text_parts.append(str(item))
        raw_text = "".join(text_parts)

    if not isinstance(raw_text, str):
        return []

    pattern = re.compile(
        r"\[(\d+)\]\s+(.*?)\s+\((.*?),(.*?)\):\n(.*?)(?=\n\[\d+\]\s+|\Z)",
        re.S,
    )
    comments: List[Dict[str, Any]] = []
    for match in pattern.finditer(raw_text):
        comment_id = int(match.group(1))
        author = match.group(2).strip()
        # MCP format: "(<timestamp>,<visibility>)"
        timestamp = match.group(3).strip()
        content = match.group(5).strip()
        role = "unknown"  # resolved later via ParticipantResolver.enrich_comments
        comments.append({
            "id": comment_id,
            "author": author,
            "timestamp": timestamp,
            "role": role,
            "content": content,
        })
    return comments


def normalize_comment_text(text: Any) -> str:
    if isinstance(text, list):
        text_parts: List[str] = []
        for item in text:
            if isinstance(item, dict):
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        return "".join(text_parts).strip()
    return str(text).strip()


def comment_content_hash(comment: Dict[str, Any]) -> str:
    normalized = normalize_comment_text(comment.get("content", ""))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def comment_handled_key(comment: Dict[str, Any]) -> str:
    """Stable dedup key: timestamp + content hash.

    MCP positional IDs ([1] = newest) shift every time a new comment is added to
    the case, so using the MCP ID as part of the key causes the agent to treat the
    same comment as a new request after each of its own replies — an infinite reply
    loop.  Timestamps are fixed by the portal and do not change when new comments
    arrive, making them a reliable stable anchor.

    Key format: "ts:<timestamp>:<content_hash>"
    Fallback (no timestamp): "nots:<mcp_id>:<content_hash>"
    """
    ts = (comment.get("timestamp") or "").strip()
    content_hash = comment_content_hash(comment)
    portal_id = str(comment.get("portal_comment_id") or "").strip()
    if portal_id:
        return f"pid:{portal_id}:{content_hash}"
    if ts:
        return f"ts:{ts}:{content_hash}"
    return f"nots:{comment.get('id', 0)}:{content_hash}"


def is_comment_handled(comment: Dict[str, Any], processed_keys: Set[str]) -> bool:
    return comment_handled_key(comment) in processed_keys


def commands_hash(commands: List[str]) -> str:
    joined = "\n".join(sorted(cmd.strip() for cmd in commands if cmd.strip()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def is_agent_reply(comment: Dict[str, Any]) -> bool:
    prefix = get_reply_prefix()
    content = normalize_comment_text(comment.get("content", "")).lstrip()
    return (
        content.startswith(prefix)
        or prefix in content[:200]
    )


def is_automated_support_boilerplate(comment: Dict[str, Any]) -> bool:
    author = normalize_comment_text(comment.get("author", "")).lower()
    return author.startswith("automated support")


def is_in_cooldown(memory: Dict[str, Any], cooldown_seconds: int) -> bool:
    if memory.get("turn_state") != TURN_COOLDOWN:
        return False
    last_reply = memory.get("last_agent_reply_at")
    if not last_reply:
        memory["turn_state"] = TURN_WAITING
        return False
    try:
        replied_at = datetime.fromisoformat(last_reply.replace("Z", "+00:00"))
    except ValueError:
        memory["turn_state"] = TURN_WAITING
        return False
    elapsed = (datetime.now(timezone.utc) - replied_at).total_seconds()
    if elapsed >= cooldown_seconds:
        memory["turn_state"] = TURN_WAITING
        return False
    memory["_cooldown_seconds_remaining"] = max(0, int(cooldown_seconds - elapsed))
    return True


def session_limit_reached(memory: Dict[str, Any], max_replies: int) -> bool:
    return memory.get("replies_this_session", 0) >= max_replies


def is_actionable_support_comment(
    comment: Dict[str, Any],
    processed_keys: Set[str],
) -> bool:
    if is_comment_handled(comment, processed_keys):
        return False
    if is_agent_reply(comment):
        return False
    if is_automated_support_boilerplate(comment):
        return False
    return True


def parse_comment_timestamp(comment: Dict[str, Any]) -> Optional[datetime]:
    raw = (comment.get("timestamp") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def comment_is_before(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True if ``a`` is chronologically older than ``b``.

    MCP ``read_case_comments_rh_portal`` numbers comments with [1] as the newest
    entry, which is the opposite of Red Hat Portal UI numbers (#127 = newest).
    Prefer timestamps; fall back to MCP id (lower id = newer).
    """
    ta = parse_comment_timestamp(a)
    tb = parse_comment_timestamp(b)
    if ta and tb:
        if ta != tb:
            return ta < tb
    elif ta and not tb:
        return True
    elif tb and not ta:
        return False
    return int(a.get("id", 0)) > int(b.get("id", 0))


def sort_comments_chronologically(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Oldest comment first."""

    def _key(comment: Dict[str, Any]) -> tuple:
        ts = parse_comment_timestamp(comment)
        cid = int(comment.get("id", 0))
        if ts is not None:
            return (0, ts, -cid)
        return (1, datetime.min.replace(tzinfo=timezone.utc), -cid)

    return sorted(comments, key=_key)


def find_latest_actionable_support_comment(
    comments: List[Dict[str, Any]],
    processed_keys: Set[str],
) -> Optional[Dict[str, Any]]:
    for comment in reversed(sort_comments_chronologically(comments)):
        if is_actionable_support_comment(comment, processed_keys):
            return comment
    return None


def collect_superseded_trigger_comments(
    comments: List[Dict[str, Any]],
    processed_keys: Set[str],
    latest: Dict[str, Any],
    *,
    resolver,
    trigger_cfg,
) -> List[Dict[str, Any]]:
    superseded: List[Dict[str, Any]] = []
    for comment in sort_comments_chronologically(comments):
        if not comment_is_before(comment, latest):
            continue
        if is_comment_handled(comment, processed_keys):
            continue
        if is_agent_reply(comment):
            continue
        role = str(comment.get("resolved_role") or resolver.resolve_role(comment))
        eligible, _ = trigger_cfg.is_eligible(comment, role)
        if eligible:
            superseded.append(comment)
    return superseded


def collect_support_candidates(
    comments: List[Dict[str, Any]],
    processed_keys: Set[str],
    *,
    analyze_fn,
    resolver,
    trigger_cfg,
) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """Return (actionable candidates, skipped comments with reason).

    Only the latest unhandled trigger-eligible comment is LLM-analyzed.
    """
    from core.trigger import find_latest_unanswered_trigger_comment

    latest = find_latest_unanswered_trigger_comment(
        comments, processed_keys, resolver, trigger_cfg
    )
    if not latest:
        return [], []

    role = str(latest.get("resolved_role") or resolver.resolve_role(latest))
    _, trigger_reason = trigger_cfg.is_eligible(latest, role)
    log_info(
        "trigger_candidate",
        comment_id=latest["id"],
        author=latest.get("author"),
        resolved_role=role,
        trigger_mode=trigger_cfg.mode,
        trigger_reason=trigger_reason,
    )

    skipped: List[Tuple[Dict[str, Any], str]] = [
        (comment, "historical_superseded")
        for comment in collect_superseded_trigger_comments(
            comments,
            processed_keys,
            latest,
            resolver=resolver,
            trigger_cfg=trigger_cfg,
        )
    ]

    analysis = analyze_fn(latest)
    if analysis.is_processable():
        enriched = dict(latest)
        enriched["_analysis"] = analysis
        enriched["_trigger_reason"] = trigger_reason
        return [enriched], skipped

    if not analysis.actionable or analysis.action_type == "no_action":
        reason = "llm_unavailable" if analysis.source == "unavailable" else "not_actionable"
        skipped.append((latest, reason))
    elif analysis.action_type in ("call_mcp", "execute_commands") and not analysis.mcp_calls:
        skipped.append((latest, "no_mcp_actions"))
    else:
        skipped.append((latest, "not_processable"))
    return [], skipped
