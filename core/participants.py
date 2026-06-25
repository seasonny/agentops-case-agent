"""Deterministic participant role resolution for case comments."""

import fnmatch
from typing import Any, Dict, List, Optional

from core.agent_settings import get_reply_prefix
from core.constants import AGENT_REPLY_PREFIX
from core.dev_mode import is_dev_mode


def _normalize_author(author: Any) -> str:
    return str(author or "").strip()


def _normalize_content(content: Any) -> str:
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(content or "").strip()


def content_has_agent_prefix(content: Any) -> bool:
    prefix = get_reply_prefix()
    text = _normalize_content(content).lstrip()
    return text.startswith(prefix) or prefix in text[:200]


class ParticipantResolver:
    """Map comment authors to roles using config rules (not LLM)."""

    def __init__(self, config: Dict[str, Any]):
        participants = config.get("participants", {})
        self.customer_authors = {
            a.lower() for a in participants.get("customer_authors", []) if str(a).strip()
        }
        self.support_authors = {
            a.lower() for a in participants.get("support_authors", []) if str(a).strip()
        }
        self.ignore_authors = {
            a.lower()
            for a in participants.get("ignore_authors", ["Automated Support"])
            if str(a).strip()
        }
        self.support_author_patterns = [
            str(p) for p in participants.get("support_author_patterns", [])
        ]
        self.customer_author_patterns = [
            str(p) for p in participants.get("customer_author_patterns", [])
        ]
        if is_dev_mode():
            self.demo_trigger_prefix = str(
                participants.get("demo_trigger_prefix", "[SE] ") or ""
            )
        else:
            self.demo_trigger_prefix = ""

    def _matches_patterns(self, author_lower: str, patterns: List[str]) -> bool:
        for pattern in patterns:
            if fnmatch.fnmatch(author_lower, pattern.lower()):
                return True
        return False

    def _map_created_by_type(self, created_by_type: str) -> Optional[str]:
        from core.case_api_models import map_created_by_type_to_role

        return map_created_by_type_to_role(created_by_type)

    def resolve_role(self, comment: Dict[str, Any], *, is_agent: bool = False) -> str:
        if is_agent or content_has_agent_prefix(comment.get("content", "")):
            return "agent"

        author = _normalize_author(comment.get("author"))
        author_lower = author.lower()
        content = _normalize_content(comment.get("content", ""))

        if self.demo_trigger_prefix and content.lstrip().startswith(self.demo_trigger_prefix):
            return "support"

        api_role = comment.get("api_role")
        if isinstance(api_role, str) and api_role in ("support", "customer", "ignored", "agent"):
            return api_role
        created_by_type = str(comment.get("created_by_type") or "").strip()
        mapped = self._map_created_by_type(created_by_type)
        if mapped:
            return mapped

        if author_lower in self.ignore_authors or author_lower.startswith("automated support"):
            return "ignored"

        if author_lower in self.support_authors:
            return "support"
        if author_lower in self.customer_authors:
            return "customer"
        if self._matches_patterns(author_lower, self.support_author_patterns):
            return "support"
        if self._matches_patterns(author_lower, self.customer_author_patterns):
            return "customer"

        if "support" in author_lower:
            return "support"
        return "customer"

    def enrich_comments(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for comment in comments:
            role = self.resolve_role(comment)
            comment["resolved_role"] = role
            comment["role"] = role
        return comments
