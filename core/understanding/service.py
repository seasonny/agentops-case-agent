"""UnderstandingService — single entry for comment interpretation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from core.comments import normalize_comment_text
from core.dangerous_command_split import split_comment_requests
from core.explicit_request import looks_like_explicit_support_request
from core.llm_client import chat_json as default_chat_json
from core.llm_client import is_llm_available as default_is_llm_available
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.understanding.models import CommentAnalysis
from core.understanding.semantic import SemanticUnderstanding

ChatJsonFn = Callable[..., Optional[Dict[str, Any]]]
IsLlmAvailableFn = Callable[[Dict[str, Any]], bool]

_LLM_TRIAGE_FAILED_MSG = (
    "LLM triage failed for this comment. Skipping automated action until the model is available."
)


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
        self._semantic = SemanticUnderstanding(
            config,
            llm_config=self.llm_config,
            mcp_tool_names=self.mcp_tool_names,
        )

    def _finalize(
        self,
        analysis: CommentAnalysis,
        blocked_commands: List[str],
    ) -> CommentAnalysis:
        analysis = _filter_dangerous_mcp_calls(analysis, self.policy)
        analysis = _attach_blocked_commands(analysis, blocked_commands)
        log_info(
            "comment_analyzed",
            source=analysis.source,
            action_type=analysis.action_type,
            actionable=analysis.actionable,
            mcp_calls=[a.tool for a in analysis.mcp_calls],
            intent=analysis.intent,
            blocked_commands=analysis.blocked_commands,
        )
        return analysis

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

        if not is_llm_available_fn(self.llm_config):
            result = self._semantic.analyze_without_llm(working_text)
            return self._finalize(result, blocked_commands)

        llm_result = self._semantic.analyze_with_llm(
            working_text,
            case_history,
            comment_author=comment_author,
            resolved_role=resolved_role,
            trigger_reason=trigger_reason,
            chat_fn=chat_fn,
        )
        if llm_result is not None:
            return self._finalize(llm_result, blocked_commands)

        if looks_like_explicit_support_request(working_text):
            return self._finalize(
                CommentAnalysis(
                    actionable=True,
                    action_type="reply_only",
                    intent="diagnostic",
                    summary=_LLM_TRIAGE_FAILED_MSG,
                    source="unavailable",
                ),
                blocked_commands,
            )

        if normalize_comment_text(working_text):
            return self._finalize(
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
