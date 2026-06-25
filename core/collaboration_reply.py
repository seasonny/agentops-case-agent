"""Collaborative reply helpers for reply_only / clarify turns."""

from __future__ import annotations

import re

# Hollow acknowledgement phrases — never post without substantive content.
_HOLLOW_SNIPPETS = (
    "已收到 Support 的說明",
    "會依建議安排後續處理",
    "我們會依指示配合後續排查",
    "有進展時再回報",
    "感謝 Support 說明，我們會再確認相關細節後回覆",
)


def _normalize_overlap_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def is_echo_of_support_request(reply_body: str, request_summary: str) -> bool:
    """True only when the reply largely copies Support's message verbatim."""
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


def is_hollow_acknowledgement(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    if len(cleaned) < 20:
        return True
    hits = sum(1 for snippet in _HOLLOW_SNIPPETS if snippet in cleaned)
    if hits >= 2:
        return True
    if hits >= 1 and len(cleaned) < 120:
        return True
    return False


def is_substantive_collaborative_reply(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or len(cleaned) < 20:
        return False
    return not is_hollow_acknowledgement(cleaned)


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
