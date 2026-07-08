"""Collaborative reply helpers for reply_only / clarify turns."""

from __future__ import annotations

import re

_MIN_COLLABORATIVE_CHARS = 20


def _normalize_overlap_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def is_echo_of_support_request(reply_body: str, request_summary: str) -> bool:
    """True when the reply largely copies Support's message verbatim."""
    body = _normalize_overlap_text(reply_body)
    summary = _normalize_overlap_text(request_summary)
    if not body or not summary or len(summary) < 12:
        return False
    if body == summary:
        return True
    if summary in body:
        return True
    if len(summary) >= 24:
        chunk_len = max(24, int(len(summary) * 0.7))
        for start in range(len(summary) - chunk_len + 1):
            if summary[start : start + chunk_len] in body:
                return True
    return False


def is_substantive_collaborative_reply(text: str) -> bool:
    """Minimal structural check — quality bar is primarily LLM collaborate + prompt."""
    cleaned = (text or "").strip()
    return len(cleaned) >= _MIN_COLLABORATIVE_CHARS


def resolve_collaborative_reply(
    *,
    customer_voice: str,
    findings: str,
    request_summary: str,
) -> str:
    """Pick the best non-echo collaborative text, or empty when none qualify."""
    for candidate in (customer_voice, findings):
        text = (candidate or "").strip()
        if not text:
            continue
        if is_echo_of_support_request(text, request_summary):
            continue
        if not is_substantive_collaborative_reply(text):
            continue
        return text
    return ""
