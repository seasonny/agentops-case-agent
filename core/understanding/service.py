"""UnderstandingService — single entry for comment interpretation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.comments import normalize_comment_text
from core.explicit_request import looks_like_explicit_support_request
from core.llm_client import chat_json as default_chat_json
from core.llm_client import is_llm_available as default_is_llm_available
from core.logging import log_info, log_warning
from core.understanding.models import CommentAnalysis
from core.understanding.semantic import SemanticUnderstanding

ChatJsonFn = Callable[..., Optional[Dict[str, Any]]]
IsLlmAvailableFn = Callable[[Dict[str, Any]], bool]

_LLM_TRIAGE_FAILED_MSG = (
    "LLM triage failed for this comment. Skipping automated action until the model is available."
)


class UnderstandingService:
    """Single entry for interpreting support comments into structured analysis."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        mcp_tool_names: Optional[List[str]] = None,
        policy_checker: Optional[Any] = None,
        allow_host_exec: bool = False,
    ):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.mcp_tool_names = mcp_tool_names or []
        self.allow_host_exec = allow_host_exec
        self._semantic = SemanticUnderstanding(
            config,
            llm_config=self.llm_config,
            mcp_tool_names=self.mcp_tool_names,
        )
        # Backward-compatible alias; governance lives in DecisionEngine.
        self.policy = policy_checker

    def _finalize(self, analysis: CommentAnalysis) -> CommentAnalysis:
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

        if not is_llm_available_fn(self.llm_config):
            result = self._semantic.analyze_without_llm(comment_text)
            return self._finalize(result)

        llm_result = self._semantic.analyze_with_llm(
            comment_text,
            case_history,
            comment_author=comment_author,
            resolved_role=resolved_role,
            trigger_reason=trigger_reason,
            chat_fn=chat_fn,
        )
        if llm_result is not None:
            return self._finalize(llm_result)

        if looks_like_explicit_support_request(comment_text):
            return self._finalize(
                CommentAnalysis(
                    actionable=True,
                    action_type="reply_only",
                    intent="diagnostic",
                    summary=_LLM_TRIAGE_FAILED_MSG,
                    source="unavailable",
                )
            )

        if normalize_comment_text(comment_text):
            return self._finalize(
                self._semantic.collaboration_reply(comment_text, source="infer")
            )

        log_warning("llm_triage_failed", fallback="no_action")
        return CommentAnalysis(
            actionable=False,
            action_type="no_action",
            summary="LLM triage 失敗，略過此留言。",
            source="unavailable",
        )
