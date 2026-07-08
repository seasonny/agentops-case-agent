"""Semantic understanding — LLM triage."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.agent_settings import get_reply_prefix
from core.comments import normalize_comment_text
from core.config import ANALYZE_PROMPT_FILE
from core.explicit_request import looks_like_explicit_support_request
from core.llm_client import chat_json as default_chat_json
from core.llm_client import is_llm_available as default_is_llm_available
from core.logging import log_warning
from core.mcp_action import build_tools_catalog
from core.mcp_policy import actions_from_payload
from core.understanding.models import VALID_ACTION_TYPES, CommentAnalysis

ChatJsonFn = Callable[..., Optional[Dict[str, Any]]]
IsLlmAvailableFn = Callable[[Dict[str, Any]], bool]

_LLM_UNAVAILABLE_EXEC_MSG = (
    "Support requested execution or output, but LLM triage is unavailable. "
    "Configure LLM or retry when the model is reachable."
)


class SemanticUnderstanding:
    """LLM-based triage; minimal deterministic fallbacks when the model is unavailable."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        llm_config: Dict[str, Any],
        mcp_tool_names: Optional[List[str]] = None,
    ):
        self.config = config
        self.llm_config = llm_config
        self.mcp_tool_names = mcp_tool_names or []

    def is_available(
        self,
        is_llm_available: IsLlmAvailableFn = default_is_llm_available,
    ) -> bool:
        return is_llm_available(self.llm_config)

    def analyze_without_llm(self, text: str) -> CommentAnalysis:
        normalized = normalize_comment_text(text)
        if get_reply_prefix() in normalized:
            return CommentAnalysis(actionable=False, action_type="no_action", source="unavailable")

        if looks_like_explicit_support_request(normalized):
            return CommentAnalysis(
                actionable=True,
                action_type="reply_only",
                intent="diagnostic",
                summary=_LLM_UNAVAILABLE_EXEC_MSG,
                source="unavailable",
            )

        if normalized:
            return self.collaboration_reply(normalized, source="unavailable")

        return CommentAnalysis(
            actionable=False,
            action_type="no_action",
            summary="LLM 未設定，無法進行語意 triage。",
            source="unavailable",
        )

    def collaboration_reply(self, text: str, *, source: str) -> CommentAnalysis:
        """Support informational / solution discussion — no MCP, but customer should respond."""
        normalized = normalize_comment_text(text)
        return CommentAnalysis(
            actionable=True,
            action_type="reply_only",
            intent="solution_discussion",
            summary=normalized[:500] if normalized else "Support update",
            source=source,
        )

    def analyze_with_llm(
        self,
        comment_text: str,
        case_history: str,
        *,
        comment_author: str = "",
        resolved_role: str = "",
        trigger_reason: str = "",
        chat_fn: ChatJsonFn = default_chat_json,
    ) -> Optional[CommentAnalysis]:
        template = _load_analyze_template()
        prompt = _render_prompt(
            template,
            comment_text=normalize_comment_text(comment_text),
            case_history=case_history or "(no prior comments)",
            agent_reply_prefix=get_reply_prefix(),
            mcp_tools_catalog=build_tools_catalog(self.mcp_tool_names),
            comment_author=comment_author or "(unknown)",
            resolved_role=resolved_role or "(unknown)",
            trigger_reason=trigger_reason or "(none)",
        )
        payload = chat_fn(
            self.llm_config,
            system_prompt=(
                "You triage Red Hat support case comments for an ops assistant. "
                "Plan MCP tool calls only from the provided catalog; "
                "do not invent tools or local shell execution outside MCP. "
                "Respond with JSON only."
            ),
            user_prompt=prompt,
        )
        if not payload:
            return None
        return _validate_analysis_payload(payload)


def _load_analyze_template() -> str:
    if ANALYZE_PROMPT_FILE.exists():
        return ANALYZE_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Analyze comment with case history. JSON only. "
        "Latest: {comment_text} History: {case_history}"
    )


def _render_prompt(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


def _normalize_action_type(action_type: str) -> str:
    if action_type == "execute_commands":
        return "call_mcp"
    return action_type


def _validate_analysis_payload(payload: Dict[str, Any]) -> Optional[CommentAnalysis]:
    action_type = _normalize_action_type(str(payload.get("action_type", "no_action")))
    if action_type not in VALID_ACTION_TYPES:
        action_type = "no_action"

    mcp_calls = actions_from_payload(payload.get("mcp_calls", []))

    questions_raw = payload.get("clarifying_questions", [])
    if not isinstance(questions_raw, list):
        questions_raw = []
    questions = [str(q).strip() for q in questions_raw if str(q).strip()]

    actionable = bool(payload.get("actionable", False))
    requires_execution = bool(
        payload.get("requires_execution", action_type == "call_mcp")
    )
    summary = str(payload.get("summary", ""))

    if action_type == "call_mcp" and not mcp_calls:
        if questions:
            action_type = "clarify"
            requires_execution = False
            actionable = True
        else:
            log_warning(
                "llm_call_mcp_without_tools",
                summary=summary[:120] if summary else "",
            )
            actionable = False
            action_type = "no_action"

    return CommentAnalysis(
        actionable=actionable,
        action_type=action_type,
        mcp_calls=mcp_calls,
        intent=str(payload.get("intent", "unknown")),
        requires_execution=requires_execution,
        summary=summary,
        clarifying_questions=questions,
        source="llm",
    )
