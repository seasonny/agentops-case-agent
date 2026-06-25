import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from core.config import MEMORY_FILE
from core.constants import TURN_COOLDOWN, TURN_OWNER_SUPPORT, TURN_WAITING
from core.logging import log_info, log_warning
from core.redaction import sanitize_for_storage


def default_memory(case_id: str = "01234567") -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "status": "POLLING",
        "latest_msg": "",
        "policy_passed": True,
        "last_comment_id": 0,
        "last_handled_support_id": 0,
        "proposed_commands": [],
        "execution_results": [],
        "policy_reason": "",
        "processed_comment_ids": [],
        "processed_handled_keys": [],
        "processed_content_hashes": [],
        "history_bootstrapped": False,
        "handled_keys_migrated": False,
        "last_agent_reply_at": None,
        "replies_this_session": 0,
        "turn_state": TURN_WAITING,
        "turn_owner": TURN_OWNER_SUPPORT,
        "last_command_hash": None,
        "last_blocker_signature": "",
        "diagnostics_history": [],
    }


def _has_legacy_handled_keys(keys: list) -> bool:
    """Return True if any key uses the old unstable MCP-ID-based format.

    Old format: "<mcp_id>:<hex_hash>"  (e.g. "27:abcd1234...")
    New format: "ts:<timestamp>:<hex_hash>" or "nots:<mcp_id>:<hex_hash>"
    """
    for key in keys:
        if isinstance(key, str) and not key.startswith(("ts:", "nots:")):
            return True
    return False


def load_agent_memory(case_id: Optional[str] = None) -> Dict[str, Any]:
    defaults = default_memory(case_id or "01234567")
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                defaults.update(loaded)
                if "last_handled_support_id" not in loaded:
                    defaults["last_handled_support_id"] = loaded.get("last_comment_id", 0)
                defaults.setdefault("processed_handled_keys", [])
                defaults.setdefault("handled_keys_migrated", False)
                # If persisted keys use the old MCP-positional-ID format, they are
                # now invalid (IDs shift on every new comment).  Force re-bootstrap
                # so the agent re-discovers handled comments using stable keys.
                if _has_legacy_handled_keys(defaults.get("processed_handled_keys", [])):
                    log_warning("legacy_handled_keys_detected_resetting_bootstrap")
                    defaults["processed_handled_keys"] = []
                    defaults["processed_comment_ids"] = []
                    defaults["history_bootstrapped"] = False
                    defaults["handled_keys_migrated"] = False
                return defaults
            log_warning("invalid_memory_format")
        except Exception as exc:
            log_warning("memory_load_failed", error=str(exc))
    return defaults


def save_agent_memory(state: Dict[str, Any]) -> None:
    clean_state = {
        "case_id": state.get("case_id", ""),
        "status": state.get("status", "POLLING"),
        "latest_msg": state.get("latest_msg", ""),
        "policy_passed": state.get("policy_passed", True),
        "last_comment_id": state.get("last_comment_id", 0),
        "last_handled_support_id": state.get("last_handled_support_id", 0),
        "proposed_commands": state.get("proposed_commands", []),
        "execution_results": state.get("execution_results", []),
        "policy_reason": state.get("policy_reason", ""),
        "processed_comment_ids": state.get("processed_comment_ids", []),
        "processed_handled_keys": state.get("processed_handled_keys", []),
        "processed_content_hashes": state.get("processed_content_hashes", []),
        "history_bootstrapped": state.get("history_bootstrapped", False),
        "handled_keys_migrated": state.get("handled_keys_migrated", False),
        "last_agent_reply_at": state.get("last_agent_reply_at"),
        "replies_this_session": state.get("replies_this_session", 0),
        "turn_state": state.get("turn_state", TURN_WAITING),
        "turn_owner": state.get("turn_owner", TURN_OWNER_SUPPORT),
        "last_command_hash": state.get("last_command_hash"),
        "last_blocker_signature": state.get("last_blocker_signature", ""),
        "diagnostics_history": state.get("diagnostics_history", []),
    }
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sanitize_for_storage(clean_state), f, indent=2, ensure_ascii=False)


def reset_agent_memory(case_id: str) -> Dict[str, Any]:
    memory = default_memory(case_id)
    save_agent_memory(memory)
    log_info("memory_reset", case_id=case_id)
    return memory


def mark_comment_handled(
    memory: Dict[str, Any],
    comment: Dict[str, Any],
    processed_ids: Set[int],
    processed_keys: Set[str],
    *,
    as_support: bool = False,
) -> None:
    from core.comments import comment_content_hash, comment_handled_key

    key = comment_handled_key(comment)
    processed_ids.add(comment["id"])
    processed_keys.add(key)
    # Legacy field kept for debugging / migration reference
    legacy_hashes = set(memory.get("processed_content_hashes", []))
    legacy_hashes.add(comment_content_hash(comment))
    memory["processed_content_hashes"] = sorted(legacy_hashes)
    memory["last_comment_id"] = max(memory.get("last_comment_id", 0), comment["id"])
    if as_support:
        memory["last_handled_support_id"] = max(
            memory.get("last_handled_support_id", 0), comment["id"]
        )
    memory["processed_comment_ids"] = sorted(processed_ids)
    memory["processed_handled_keys"] = sorted(processed_keys)
    memory["status"] = "POLLING"
    save_agent_memory(memory)


def record_agent_reply(memory: Dict[str, Any], command_hash: Optional[str] = None) -> None:
    memory["last_agent_reply_at"] = datetime.now(timezone.utc).isoformat()
    memory["replies_this_session"] = memory.get("replies_this_session", 0) + 1
    memory["turn_state"] = TURN_COOLDOWN
    memory["turn_owner"] = TURN_OWNER_SUPPORT
    if command_hash:
        memory["last_command_hash"] = command_hash
    save_agent_memory(memory)


def maybe_unmark_failed_execution(
    memory: Dict[str, Any],
    comments: List[Dict[str, Any]],
) -> None:
    from core.comments import (
        comment_handled_key,
        normalize_comment_text,
        sort_comments_chronologically,
    )

    commands = memory.get("proposed_commands", [])
    results = memory.get("execution_results", [])
    if not commands or not results:
        return
    if not all(not str(result).strip() for result in results):
        return

    latest_msg = normalize_comment_text(memory.get("latest_msg", ""))
    if not latest_msg:
        return

    processed_ids = set(memory.get("processed_comment_ids", []))
    processed_keys = set(memory.get("processed_handled_keys", []))
    for comment in sort_comments_chronologically(comments):
        if normalize_comment_text(comment.get("content", "")) != latest_msg:
            continue
        key = comment_handled_key(comment)
        if key not in processed_keys and comment["id"] not in processed_ids:
            continue
        processed_ids.discard(comment["id"])
        processed_keys.discard(key)
        support_id = memory.get("last_handled_support_id", 0)
        if comment["id"] == support_id:
            memory["last_handled_support_id"] = max(0, support_id - 1)
        log_info("retry_empty_execution", comment_id=comment["id"])
        break

    memory["processed_comment_ids"] = sorted(processed_ids)
    memory["processed_handled_keys"] = sorted(processed_keys)


def migrate_handled_keys_from_legacy(
    memory: Dict[str, Any],
    comments: List[Dict[str, Any]],
    processed_keys: Set[str],
) -> None:
    if memory.get("handled_keys_migrated"):
        return
    id_set = set(memory.get("processed_comment_ids", []))
    for comment in comments:
        if comment["id"] in id_set:
            from core.comments import comment_handled_key

            processed_keys.add(comment_handled_key(comment))
    memory["handled_keys_migrated"] = True
    memory["processed_handled_keys"] = sorted(processed_keys)
    log_info("handled_keys_migrated", key_count=len(processed_keys))


def bootstrap_comment_history(
    memory: Dict[str, Any],
    comments: List[Dict[str, Any]],
    processed_keys: Set[str],
    *,
    resolver=None,
    trigger_cfg=None,
) -> None:
    from core.comments import (
        comment_handled_key,
        comment_is_before,
        find_latest_actionable_support_comment,
        is_agent_reply,
        is_automated_support_boilerplate,
        is_comment_handled,
        sort_comments_chronologically,
    )
    from core.trigger import find_last_unanswered_trigger_comment

    if memory.get("history_bootstrapped"):
        return

    processed_ids = set(memory.get("processed_comment_ids", []))

    if not processed_ids and not processed_keys:
        unanswered = None
        if resolver is not None and trigger_cfg is not None:
            unanswered = find_last_unanswered_trigger_comment(
                comments, resolver, trigger_cfg
            )
        unanswered_key = comment_handled_key(unanswered) if unanswered else None

        max_id = 0
        for comment in comments:
            max_id = max(max_id, comment["id"])
            if unanswered_key and comment_handled_key(comment) == unanswered_key:
                continue  # intentionally left unhandled
            processed_keys.add(comment_handled_key(comment))

        memory["history_bootstrapped"] = True
        memory["last_comment_id"] = max(memory.get("last_comment_id", 0), max_id)
        memory["processed_handled_keys"] = sorted(processed_keys)
        log_info(
            "history_bootstrapped",
            mode="fresh",
            comment_count=len(comments),
            last_id=max_id,
            unanswered_comment_id=unanswered["id"] if unanswered else None,
        )
        return

    latest = find_latest_actionable_support_comment(comments, processed_keys)
    marked = 0
    for comment in sort_comments_chronologically(comments):
        if is_agent_reply(comment) or is_automated_support_boilerplate(comment):
            key = comment_handled_key(comment)
            if key not in processed_keys:
                processed_keys.add(key)
                marked += 1
            continue
        if latest and comment_is_before(comment, latest):
            if not is_comment_handled(comment, processed_keys):
                processed_keys.add(comment_handled_key(comment))
                marked += 1

    memory["history_bootstrapped"] = True
    memory["processed_handled_keys"] = sorted(processed_keys)
    log_info("history_bootstrapped", mode="partial", marked=marked)
