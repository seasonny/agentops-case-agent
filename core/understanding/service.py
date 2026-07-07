"""UnderstandingService — single entry for comment interpretation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from core.comments import normalize_comment_text
from core.dangerous_command_split import split_comment_requests
from core.llm_client import chat_json as default_chat_json
from core.llm_client import is_llm_available as default_is_llm_available
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.shell_diagnostics import (
    extract_shell_commands_from_text,
    looks_like_explicit_support_request,
)
from core.understanding.action_inference import ActionInference
from core.understanding.models import CommentAnalysis
from core.understanding.semantic import SemanticUnderstanding

ChatJsonFn = Callable[..., Optional[Dict[str, Any]]]
IsLlmAvailableFn = Callable[[Dict[str, Any]], bool]


def _attach_blocked_commands(
    analysis: CommentAnalysis,
    blocked_commands: List[str],
) -> CommentAnalysis:
    if not blocked_commands:
        return analysis
    return CommentAnalysis(
        actionable=analysis.actionable,
        action_type=analysis.action_type,
        mcp_calls=list(analysis.mcp_calls),
        intent=analysis.intent,
        requires_execution=analysis.requires_execution,
        summary=analysis.summary,
        clarifying_questions=list(analysis.clarifying_questions),
        blocked_commands=list(blocked_commands),
        source=analysis.source,
    )


def _filter_dangerous_mcp_calls(
    analysis: CommentAnalysis,
    policy: MCPPolicyChecker,
) -> CommentAnalysis:
    kept: List[MCPAction] = []
    for action in analysis.mcp_calls:
        probe_parts = [action.tool, action.label]
        argv = action.arguments.get("argv") or action.arguments.get("command")
        if isinstance(argv, list):
            probe_parts.extend(str(part) for part in argv)
        probe = " ".join(probe_parts)
        if policy.is_dangerous_command(probe)[0]:
            continue
        kept.append(action)
    if len(kept) == len(analysis.mcp_calls):
        return analysis
    if not kept and analysis.action_type == "call_mcp":
        return CommentAnalysis(
            actionable=True,
            action_type="reply_only",
            intent=analysis.intent,
            summary=analysis.summary or "Requested diagnostics could not be mapped safely.",
            clarifying_questions=analysis.clarifying_questions,
            blocked_commands=list(analysis.blocked_commands),
            source=f"{analysis.source}+filtered",
        )
    return CommentAnalysis(
        actionable=analysis.actionable,
        action_type=analysis.action_type,
        mcp_calls=kept,
        intent=analysis.intent,
        requires_execution=bool(kept),
        summary=analysis.summary,
        clarifying_questions=analysis.clarifying_questions,
        blocked_commands=list(analysis.blocked_commands),
        source=f"{analysis.source}+filtered",
    )


class UnderstandingService:
    """Single entry for interpreting support comments into structured analysis."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        mcp_tool_names: Optional[List[str]] = None,
        policy_checker: Optional[MCPPolicyChecker] = None,
        allow_host_exec: bool = False,
    ):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.mcp_tool_names = mcp_tool_names or []
        self.policy = policy_checker or MCPPolicyChecker()
        self.allow_host_exec = allow_host_exec
        self._action_inference = ActionInference(
            config,
            mcp_tool_names=self.mcp_tool_names,
            policy=self.policy,
            allow_host_exec=allow_host_exec,
        )
        self._semantic = SemanticUnderstanding(
            config,
            llm_config=self.llm_config,
            mcp_tool_names=self.mcp_tool_names,
            action_inference=self._action_inference,
            allow_host_exec=allow_host_exec,
        )

    def _finalize_routed(
        self,
        routed: CommentAnalysis,
        blocked_commands: List[str],
    ) -> CommentAnalysis:
        routed = _filter_dangerous_mcp_calls(routed, self.policy)
        routed = _attach_blocked_commands(routed, blocked_commands)
        log_info(
            "comment_analyzed",
            source=routed.source,
            action_type=routed.action_type,
            actionable=routed.actionable,
            mcp_calls=[a.tool for a in routed.mcp_calls],
            intent=routed.intent,
            blocked_commands=routed.blocked_commands,
        )
        return routed

    def _evaluate_dangerous_split(
        self,
        comment_text: str,
    ) -> Tuple[Optional[CommentAnalysis], str, List[str]]:
        split = split_comment_requests(
            comment_text,
            self.policy.is_dangerous_command,
            dangerous_handling=self.policy.dangerous_handling,
        )
        if not split.blocked_lines and not split.reject_entire:
            return None, comment_text, []

        if split.reject_entire:
            matched = split.blocked_lines[0] if split.blocked_lines else comment_text
            log_info(
                "dangerous_command_precheck",
                matched=matched,
                handling=self.policy.dangerous_handling,
                blocked_count=len(split.blocked_lines),
            )
            return (
                CommentAnalysis(
                    actionable=True,
                    action_type="dangerous_command",
                    intent="safety_block",
                    requires_execution=False,
                    summary=f"Support requested blocked OS command: {matched}",
                    blocked_commands=list(split.blocked_lines),
                    source="policy",
                ),
                comment_text,
                list(split.blocked_lines),
            )

        log_info(
            "dangerous_command_skipped",
            blocked=split.blocked_lines,
            safe=split.safe_lines,
            handling=self.policy.dangerous_handling,
        )
        working_text = split.safe_text or comment_text
        return None, working_text, list(split.blocked_lines)

    def analyze(
        self,
        comment_text: str,
        *,
        case_history: str = "",
        comment_author: str = "",
        resolved_role: str = "",
        trigger_reason: str = "",
        chat_fn: ChatJsonFn = default_chat_json,
        is_llm_available_fn: IsLlmAvailableFn = default_is_llm_available,
    ) -> CommentAnalysis:
        if not normalize_comment_text(comment_text):
            return CommentAnalysis(actionable=False, action_type="no_action", source="none")

        blocked_early, working_text, blocked_commands = self._evaluate_dangerous_split(
            comment_text
        )
        if blocked_early is not None:
            return blocked_early

        routed = self._action_inference.try_deterministic_route(working_text)
        if routed is not None:
            return self._finalize_routed(routed, blocked_commands)

        if not is_llm_available_fn(self.llm_config):
            result = self._semantic.analyze_without_llm(working_text)
            result = _filter_dangerous_mcp_calls(result, self.policy)
            return _attach_blocked_commands(result, blocked_commands)

        llm_result = self._semantic.analyze_with_llm(
            working_text,
            case_history,
            comment_author=comment_author,
            resolved_role=resolved_role,
            trigger_reason=trigger_reason,
            chat_fn=chat_fn,
        )
        if llm_result is not None:
            llm_result = _filter_dangerous_mcp_calls(llm_result, self.policy)
            llm_result = _attach_blocked_commands(llm_result, blocked_commands)
            log_info(
                "comment_analyzed",
                source=llm_result.source,
                action_type=llm_result.action_type,
                actionable=llm_result.actionable,
                mcp_calls=[a.tool for a in llm_result.mcp_calls],
                intent=llm_result.intent,
                blocked_commands=llm_result.blocked_commands,
                comment_author=comment_author or None,
                resolved_role=resolved_role or None,
                trigger_reason=trigger_reason or None,
            )
            return llm_result

        if looks_like_explicit_support_request(working_text):
            cluster_inferred = self._action_inference.infer_cluster_read_fallback(working_text)
            if cluster_inferred:
                result = CommentAnalysis(
                    actionable=True,
                    action_type="call_mcp",
                    mcp_calls=cluster_inferred,
                    intent="diagnostic",
                    requires_execution=True,
                    summary="Support request (cluster read infer after LLM failure).",
                    source="infer",
                )
                result = _filter_dangerous_mcp_calls(result, self.policy)
                return _attach_blocked_commands(result, blocked_commands)
            shell_commands = extract_shell_commands_from_text(working_text)
            inferred = self._action_inference.infer_shell_diag_actions(shell_commands)
            if inferred:
                route = inferred[0].tool
                result = CommentAnalysis(
                    actionable=True,
                    action_type="call_mcp",
                    mcp_calls=inferred,
                    intent="diagnostic",
                    requires_execution=True,
                    summary=f"Support request ({route} infer after LLM failure).",
                    source="infer",
                )
                result = _filter_dangerous_mcp_calls(result, self.policy)
                return _attach_blocked_commands(result, blocked_commands)
            result = CommentAnalysis(
                actionable=True,
                action_type="reply_only",
                intent="diagnostic",
                summary="Support requested diagnostics (LLM triage failed).",
                source="unavailable",
            )
            return _attach_blocked_commands(result, blocked_commands)

        if normalize_comment_text(working_text):
            return _attach_blocked_commands(
                self._semantic.collaboration_reply(working_text, source="infer"),
                blocked_commands,
            )

        log_warning("llm_triage_failed", fallback="no_action")
        return CommentAnalysis(
            actionable=False,
            action_type="no_action",
            summary="LLM triage 失敗，略過此留言。",
            source="unavailable",
        )
