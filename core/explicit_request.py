"""Lightweight heuristics for demo-mode trigger only — not triage routing."""

from __future__ import annotations

EXPLICIT_REQUEST_MARKERS = (
    "plz ",
    "please ",
    "請執行",
    "請輸出",
    "請上傳",
    "請提供",
    "請回傳",
    "run the following",
    "update the following output",
)


def looks_like_explicit_support_request(text: str) -> bool:
    """True when a comment likely asks the agent to run something or return output.

    Used only for demo trigger eligibility and no-LLM fallbacks — not for MCP routing.
    """
    normalized = (text or "").strip()
    if not normalized:
        return False
    if "```" in normalized:
        return True
    lowered = normalized.lower()
    return any(marker in lowered for marker in EXPLICIT_REQUEST_MARKERS)
