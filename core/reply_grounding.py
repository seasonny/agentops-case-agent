"""Verify replies that cite execution output are grounded in real MCP results."""

import re
from typing import List, Sequence, Tuple

from core.mcp_action import MCPAction

_SUCCESS_OUTPUT_PATTERNS = [
    re.compile(r"ANSWER\s+SECTION", re.I),
    re.compile(r";\s*<<>>\s*DiG", re.I),
    re.compile(r"\d+\s+bytes\s+from", re.I),
    re.compile(r"icmp_seq=", re.I),
    re.compile(r"Server:\s+\S+", re.I),
]

_FAILURE_MARKERS = (
    "error:",
    "failed",
    "exit_code: 1",
    "exit_code: 2",
    "exit_code: 3",
    "command not allowed",
    "(mcp 工具無文字輸出)",
    "no such host",
    "unable to connect",
    "connection refused",
    "timeout",
    "iserror",
)

_DRY_RUN_MARKER = "(dry-run)"


def _results_blob(results: Sequence[str]) -> str:
    return "\n".join(str(item) for item in results if item)


def results_indicate_failure(results: Sequence[str]) -> bool:
    blob = _results_blob(results).lower()
    if not blob.strip():
        return True
    return any(marker in blob for marker in _FAILURE_MARKERS)


def reply_claims_diagnostic_output(reply: str) -> bool:
    return any(pattern.search(reply) for pattern in _SUCCESS_OUTPUT_PATTERNS)


def _significant_result_lines(results: Sequence[str], *, min_len: int = 8) -> List[str]:
    lines: List[str] = []
    for result in results:
        for raw in str(result).splitlines():
            line = raw.strip()
            if len(line) < min_len:
                continue
            if _DRY_RUN_MARKER in line.lower():
                continue
            lines.append(line)
    return lines


def has_substantive_overlap(reply: str, results: Sequence[str]) -> bool:
    reply_lower = reply.lower()
    for line in _significant_result_lines(results):
        needle = line.lower()
        if needle in reply_lower:
            return True
        if len(needle) > 40 and needle[:40] in reply_lower:
            return True
    blob = _results_blob(results).strip()
    if len(blob) >= 20:
        preview = blob[: min(100, len(blob))].lower()
        if preview in reply_lower:
            return True
    return False


def check_execution_grounding(
    reply_text: str,
    *,
    action_type: str,
    execution_results: Sequence[str],
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """Return ``(passed, reason)``. Skips when grounding does not apply."""
    if dry_run:
        return True, "skipped_dry_run"
    if action_type != "call_mcp":
        return True, "skipped_action_type"
    if not (reply_text or "").strip():
        return True, "ok"

    results = list(execution_results or [])
    if reply_claims_diagnostic_output(reply_text):
        if not results:
            return False, "ungrounded_execution_output:no_results"
        if results_indicate_failure(results):
            return False, "ungrounded_execution_output:success_claim_on_failure"
        if not has_substantive_overlap(reply_text, results):
            return False, "ungrounded_execution_output:no_overlap"

    return True, "ok"


def build_grounded_fallback_reply(
    *,
    reply_prefix: str,
    request_summary: str,
    mcp_actions: List[MCPAction],
    execution_results: Sequence[str],
) -> str:
    """Deterministic reply that quotes only real MCP output."""
    parts = [
        reply_prefix,
        f"針對：{request_summary or 'Support 請求'}",
        "",
        "以下為 MCP 實際執行輸出（原始結果，供排查參考）：",
        "",
    ]
    actions = mcp_actions or []
    results = list(execution_results) or []
    if not actions:
        parts.append("\n".join(str(r) for r in results) if results else "(無執行輸出)")
    else:
        for index, action in enumerate(actions):
            output = results[index] if index < len(results) else "(無輸出)"
            parts.append(f"**{action.display_label()}**")
            parts.append(str(output))
            parts.append("")
    return "\n".join(parts).strip()
