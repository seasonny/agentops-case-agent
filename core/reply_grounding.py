"""Verify replies that cite execution output are grounded in real MCP results."""

from typing import List, Sequence, Tuple

from core.mcp_action import MCPAction

# Generic markers that a reply is quoting tool output (not scenario-specific).
_TOOL_OUTPUT_MARKERS = (
    "exit_code:",
    "--- stdout ---",
    "--- stderr ---",
    "answer section",
)

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


def reply_appears_to_quote_tool_output(reply: str) -> bool:
    lower = (reply or "").lower()
    return any(marker in lower for marker in _TOOL_OUTPUT_MARKERS)


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
    quotes_output = reply_appears_to_quote_tool_output(reply_text)

    if quotes_output and not results:
        return False, "ungrounded_execution_output:no_results"

    if not results:
        return True, "ok"

    if results_indicate_failure(results):
        if has_substantive_overlap(reply_text, results):
            return True, "ok"
        if quotes_output:
            return False, "ungrounded_execution_output:success_claim_on_failure"
        return True, "ok"

    if quotes_output and not has_substantive_overlap(reply_text, results):
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
