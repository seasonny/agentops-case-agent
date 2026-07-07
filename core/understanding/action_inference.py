"""Deterministic action inference — maps comment text to suggested MCP actions.

Produces *suggested* actions only. Policy allow/deny is evaluated elsewhere.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.cluster_read_routing import (
    infer_cluster_read_actions_from_text,
    is_cluster_read_only_request,
)
from domain.case.collection_flow import (
    infer_explicit_upload_analysis,
    infer_must_gather_analysis,
)
from core.logging import log_info
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.shell_diagnostics import (
    extract_shell_commands_from_text,
    infer_shell_diag_actions,
    is_shell_only_request,
    needs_shell_diag_routing_override,
)
from core.understanding.models import CommentAnalysis


class ActionInference:
    """Deterministic routing: shell, cluster read, collection/upload."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        mcp_tool_names: Optional[List[str]] = None,
        policy: Optional[MCPPolicyChecker] = None,
        allow_host_exec: bool = False,
    ):
        self.config = config
        self.mcp_tool_names = mcp_tool_names or []
        self.policy = policy or MCPPolicyChecker()
        self.allow_host_exec = allow_host_exec

    def try_deterministic_route(self, comment_text: str) -> Optional[CommentAnalysis]:
        """Try cluster read, shell-only, then collection routes in priority order."""
        routed = self._infer_cluster_read(comment_text)
        if routed is not None:
            return routed
        routed = self._infer_shell_only(comment_text)
        if routed is not None:
            return routed
        case_id = str(self.config.get("case_id", "") or "").strip()
        return self._infer_collection(comment_text, case_id=case_id)

    def apply_shell_diag_override(
        self,
        analysis: CommentAnalysis,
        comment_text: str,
    ) -> CommentAnalysis:
        if analysis.action_type != "call_mcp":
            return analysis
        if not needs_shell_diag_routing_override(analysis.mcp_calls, comment_text):
            return analysis

        shell_commands = extract_shell_commands_from_text(comment_text)
        inferred = infer_shell_diag_actions(
            shell_commands,
            self.config,
            allow_host_exec=self.allow_host_exec,
        )
        if not inferred:
            return analysis

        route = inferred[0].tool
        prior_tools = [action.tool for action in analysis.mcp_calls]
        log_info(
            "shell_diag_routing_override",
            prior_tools=prior_tools,
            route=route,
            commands=shell_commands,
        )
        source = (
            analysis.source
            if analysis.source.endswith("+route")
            else f"{analysis.source}+route"
        )
        return CommentAnalysis(
            actionable=True,
            action_type="call_mcp",
            mcp_calls=inferred,
            intent=analysis.intent or "diagnostic",
            requires_execution=True,
            summary=analysis.summary or f"Shell diagnostics routed to {route}.",
            clarifying_questions=analysis.clarifying_questions,
            source=source,
        )

    def infer_cluster_read_fallback(self, comment_text: str) -> List[MCPAction]:
        return infer_cluster_read_actions_from_text(comment_text)

    def infer_shell_diag_actions(self, shell_commands: List[str]) -> List[MCPAction]:
        return infer_shell_diag_actions(
            shell_commands,
            self.config,
            allow_host_exec=self.allow_host_exec,
        )

    def _infer_cluster_read(self, comment_text: str) -> Optional[CommentAnalysis]:
        if not is_cluster_read_only_request(comment_text):
            return None
        inferred = infer_cluster_read_actions_from_text(comment_text)
        if not inferred:
            return None
        log_info(
            "cluster_read_deterministic_route",
            commands=[a.label for a in inferred],
            tools=[a.tool for a in inferred],
        )
        return CommentAnalysis(
            actionable=True,
            action_type="call_mcp",
            mcp_calls=inferred,
            intent="diagnostic",
            requires_execution=True,
            summary="Support requested cluster read queries.",
            source="route",
        )

    def _infer_shell_only(self, comment_text: str) -> Optional[CommentAnalysis]:
        if not is_shell_only_request(comment_text):
            return None
        shell_commands = extract_shell_commands_from_text(comment_text)
        inferred = infer_shell_diag_actions(
            shell_commands,
            self.config,
            allow_host_exec=self.allow_host_exec,
        )
        if not inferred:
            return None
        route = inferred[0].tool
        log_info("shell_diag_deterministic_route", route=route, commands=shell_commands)
        return CommentAnalysis(
            actionable=True,
            action_type="call_mcp",
            mcp_calls=inferred,
            intent="diagnostic",
            requires_execution=True,
            summary=f"Support requested shell diagnostics via {route}.",
            source="route",
        )

    def _infer_collection(self, comment_text: str, *, case_id: str) -> Optional[CommentAnalysis]:
        upload = infer_explicit_upload_analysis(
            comment_text,
            case_id,
            mcp_tool_names=self.mcp_tool_names,
            policy=self.policy,
        )
        if upload:
            log_info(
                "collection_deterministic_route",
                route="explicit_upload",
                tools=[a.tool for a in upload["mcp_calls"]],
            )
            return CommentAnalysis(
                actionable=True,
                action_type="call_mcp",
                mcp_calls=list(upload["mcp_calls"]),
                intent="diagnostic",
                requires_execution=True,
                summary=str(upload["summary"]),
                source="route",
            )

        must_gather = infer_must_gather_analysis(
            comment_text,
            mcp_tool_names=self.mcp_tool_names,
            policy=self.policy,
        )
        if must_gather:
            log_info(
                "collection_deterministic_route",
                route="must_gather",
                tools=[a.tool for a in must_gather["mcp_calls"]],
            )
            return CommentAnalysis(
                actionable=True,
                action_type="call_mcp",
                mcp_calls=list(must_gather["mcp_calls"]),
                intent="diagnostic",
                requires_execution=True,
                summary=str(must_gather["summary"]),
                source="route",
            )
        return None
