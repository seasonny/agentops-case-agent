"""Deterministic trigger rules: when should the agent act on a comment?"""

from typing import Any, Dict, List, Optional, Set, Tuple

from core.dev_mode import is_dev_mode
from core.participants import ParticipantResolver
from core.shell_diagnostics import looks_like_explicit_support_request


class TriggerConfig:
    """Gate which comments may invoke triage/workflow.

    Default (customer): production — act on Support comments only.
    Dev (AGENT_DEV_MODE=1): demo — one-person testing with optional prefix.
    """

    def __init__(self, config: Dict[str, Any]):
        trigger = config.get("trigger", {})
        configured_mode = str(trigger.get("mode", "")).strip().lower()
        if configured_mode in ("demo", "production"):
            self.mode = configured_mode
        elif is_dev_mode():
            self.mode = "demo"
        else:
            self.mode = "production"

        default_ignore_customer = self.mode == "production"
        self.ignore_customer_comments = bool(
            trigger.get("ignore_customer_comments", default_ignore_customer)
        )

        default_roles = ["support"] if self.mode == "production" else ["support", "any"]
        raw_roles = trigger.get("trigger_on_roles", default_roles)
        if isinstance(raw_roles, list):
            self.trigger_on_roles = {str(r).lower() for r in raw_roles}
        else:
            self.trigger_on_roles = set(default_roles)

        self.require_explicit_request_in_demo = bool(
            trigger.get("require_explicit_request_in_demo", True)
        )

    def is_eligible(
        self,
        comment: Dict[str, Any],
        role: str,
    ) -> Tuple[bool, str]:
        if role == "ignored":
            return False, "ignored_author"
        if role == "agent":
            return False, "agent_reply"

        content = comment.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        content = str(content or "")

        if self.mode == "production":
            if self.ignore_customer_comments and role == "customer":
                return False, "customer_internal"
            if role != "support":
                return False, "not_support_role"
            return True, "support_unanswered"

        # demo — one-person two-role testing
        if role == "support":
            return True, "demo_support_role"

        if role == "customer":
            if self.require_explicit_request_in_demo:
                if looks_like_explicit_support_request(content):
                    return True, "demo_explicit_request"
                return False, "customer_no_explicit_request"
            if "any" in self.trigger_on_roles:
                return True, "demo_customer_allowed"
            return False, "customer_no_trigger"

        return False, "not_trigger_eligible"


def _comment_role(comment: Dict[str, Any], resolver: ParticipantResolver) -> str:
    return str(comment.get("resolved_role") or resolver.resolve_role(comment))


def find_last_unanswered_trigger_comment(
    comments: List[Dict[str, Any]],
    resolver: ParticipantResolver,
    trigger_cfg: TriggerConfig,
) -> Optional[Dict[str, Any]]:
    """Newest trigger-eligible comment with no agent reply after it (bootstrap)."""
    from core.comments import is_agent_reply, sort_comments_chronologically

    for comment in reversed(sort_comments_chronologically(comments)):
        if is_agent_reply(comment):
            return None
        role = _comment_role(comment, resolver)
        eligible, _ = trigger_cfg.is_eligible(comment, role)
        if eligible:
            return comment
    return None


def find_latest_unanswered_trigger_comment(
    comments: List[Dict[str, Any]],
    processed_keys: Set[str],
    resolver: ParticipantResolver,
    trigger_cfg: TriggerConfig,
) -> Optional[Dict[str, Any]]:
    """Newest unhandled trigger-eligible comment (no newer agent reply at tail)."""
    from core.comments import (
        is_agent_reply,
        is_comment_handled,
        sort_comments_chronologically,
    )

    for comment in reversed(sort_comments_chronologically(comments)):
        if is_agent_reply(comment):
            return None
        role = _comment_role(comment, resolver)
        eligible, _ = trigger_cfg.is_eligible(comment, role)
        if not eligible:
            continue
        if is_comment_handled(comment, processed_keys):
            continue
        return comment
    return None
