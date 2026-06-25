"""Per-turn execution context — avoid stale MCP results leaking across poll cycles."""

from typing import Any, Dict, List, Sequence

from core.mcp_action import MCPAction

TEXT_ONLY_COMPOSE_ACTIONS = frozenset(
    {
        "reply_only",
        "clarify",
        "no_action",
        "approval_required",
        "dangerous_command",
    }
)


def reset_turn_execution_state(
    memory: Dict[str, Any],
    *,
    action_type: str,
    mcp_actions: Sequence[MCPAction],
) -> None:
    """Clear prior-turn MCP output before a new workflow invoke."""
    memory["execution_results"] = []
    memory["interpretation_findings"] = ""
    memory["interpretation_next_steps"] = []
    memory["needs_more_evidence"] = False
    memory["follow_up_mcp_actions"] = []
    memory["investigate_step"] = 0
    memory["convergence_reason"] = ""
    memory["solution_summary"] = ""
    memory["diag_bundle_uploaded"] = False
    memory["diag_bundle_filename"] = ""
    memory["diag_bundle_path"] = ""
    memory["diag_bundle_upload_result"] = ""
    memory["collection_uploaded"] = False
    memory["collection_upload_filename"] = ""
    memory["collection_upload_path"] = ""
    memory["collection_upload_result"] = ""
    memory["attachment_verified"] = False
    memory["attachment_verify_detail"] = ""
    memory["approval_required"] = False
    memory["approval_pending"] = []
    memory["collaboration_customer_voice"] = ""
    memory["collaboration_source"] = ""
    memory["convergence_signal"] = ""
    memory["compose_skip_reason"] = ""
    memory["reply_skipped_reason"] = ""

    serialized = [
        {"tool": a.tool, "arguments": a.arguments, "label": a.label}
        for a in mcp_actions
        if a.tool
    ]
    if action_type == "call_mcp" and serialized:
        memory["all_mcp_actions"] = list(serialized)
    else:
        memory["all_mcp_actions"] = []


def mcp_results_for_compose(
    *,
    action_type: str,
    mcp_actions: List[MCPAction],
    mcp_results: List[str],
) -> List[str]:
    """Return MCP results only when this turn actually executed diagnostics."""
    if not mcp_actions:
        return []
    if action_type in TEXT_ONLY_COMPOSE_ACTIONS:
        return []
    return list(mcp_results or [])
