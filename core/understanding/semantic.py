"""Semantic understanding — LLM triage and non-routing interpretation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.agent_settings import get_reply_prefix
from core.clarify_templates import (
    enrich_clarifying_questions,
    should_use_clarify_instead_of_reply_only,
)
from core.comments import normalize_comment_text
from core.config import ANALYZE_PROMPT_FILE
from core.llm_client import chat_json as default_chat_json
from core.llm_client import is_llm_available as default_is_llm_available
from core.logging import log_info, log_warning
from core.mcp_action import build_tools_catalog
from core.mcp_policy import actions_from_payload
from core.shell_diagnostics import (
    extract_shell_commands_from_text,
    looks_like_explicit_support_request,
)
from core.understanding.action_inference import ActionInference
from core.understanding.models import VALID_ACTION_TYPES, CommentAnalysis

ChatJsonFn = Callable[..., Optional[Dict[str, Any]]]
IsLlmAvailableFn = Callable[[Dict[str, Any]], bool]


class SemanticUnderstanding:
    """LLM-based triage and semantic fallbacks when models are unavailable."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        llm_config: Dict[str, Any],
        mcp_tool_names: Optional[List[str]] = None,
        action_inference: ActionInference,
        allow_host_exec: bool = False,
    ):
        self.config = config
        self.llm_config = llm_config
        self.mcp_tool_names = mcp_tool_names or []
        self.action_inference = action_inference
        self.allow_host_exec = allow_host_exec

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
            shell_commands = extract_shell_commands_from_text(normalized)
            inferred = self.action_inference.infer_shell_diag_actions(shell_commands)
            if inferred:
                route = inferred[0].tool
                return CommentAnalysis(
                    actionable=True,
                    action_type="call_mcp",
                    mcp_calls=inferred,
                    intent="diagnostic",
                    requires_execution=True,
                    summary=f"Support request ({route} infer, LLM unavailable).",
                    source="infer",
                )
            return CommentAnalysis(
                actionable=True,
                action_type="reply_only",
                intent="diagnostic",
                summary="Support requested diagnostics (LLM unavailable).",
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
                "Plan MCP tool calls only; do not suggest local shell execution. "
                "Use pods_exec for nslookup/ping/dig when cluster pod is configured; "
                "otherwise use exec_argv for host/bastion diagnostics when available. "
                "Respond with JSON only."
            ),
            user_prompt=prompt,
        )
        if not payload:
            return None
        analysis = _validate_analysis_payload(
            payload,
            comment_text=comment_text,
            action_inference=self.action_inference,
            allow_host_exec=self.allow_host_exec,
        )
        if analysis is None:
            return None
        return _finalize_semantic_analysis(
            analysis,
            comment_text=comment_text,
            action_inference=self.action_inference,
            allow_host_exec=self.allow_host_exec,
            mcp_tool_names=self.mcp_tool_names,
        )


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


def _shell_commands_from_payload(payload: Dict[str, Any], comment_text: str) -> List[str]:
    legacy_commands = payload.get("commands", [])
    commands: List[str] = []
    if isinstance(legacy_commands, list):
        commands.extend(str(c).strip() for c in legacy_commands if str(c).strip())
    if not commands:
        commands = extract_shell_commands_from_text(comment_text)
    return commands


def _apply_clarify_enrichment(
    analysis: CommentAnalysis,
    comment_text: str,
    *,
    mcp_tool_names: List[str],
    allow_host_exec: bool,
) -> CommentAnalysis:
    action_type = analysis.action_type
    if should_use_clarify_instead_of_reply_only(
        comment_text,
        mcp_tool_names=mcp_tool_names,
    ) and action_type == "reply_only":
        action_type = "clarify"

    if action_type not in ("clarify", "reply_only"):
        return analysis

    questions = enrich_clarifying_questions(
        comment_text,
        action_type=action_type,
        existing_questions=analysis.clarifying_questions,
        mcp_tool_names=mcp_tool_names,
        allow_host_exec=allow_host_exec,
    )
    if action_type == analysis.action_type and questions == analysis.clarifying_questions:
        return analysis

    return CommentAnalysis(
        actionable=True,
        action_type="clarify" if action_type == "clarify" else analysis.action_type,
        mcp_calls=list(analysis.mcp_calls),
        intent=analysis.intent,
        requires_execution=False,
        summary=analysis.summary,
        clarifying_questions=questions,
        blocked_commands=list(analysis.blocked_commands),
        source=analysis.source if analysis.source else "clarify_template",
    )


def _reply_only_for_unmapped(
    *,
    summary: str,
    questions: List[str],
    shell_commands: List[str],
    source: str,
    allow_host_exec: bool,
) -> CommentAnalysis:
    cmd_preview = ", ".join(shell_commands[:3]) if shell_commands else "requested diagnostics"
    questions = questions or []
    if not questions:
        if allow_host_exec:
            questions = [
                "若需從叢集內執行 nslookup/ping，請提供目標 Pod 的 namespace 與名稱，"
                "或於 config 設定 diagnostics.pods_exec。"
            ]
        else:
            questions = [
                "若需從叢集內執行 nslookup/ping，請提供目標 Pod 的 namespace 與名稱，"
                "或於 config 設定 diagnostics.pods_exec；"
                "若需本機/跳板機執行，請在 agent_config.json 啟用 exec MCP provider。"
            ]
    return CommentAnalysis(
        actionable=True,
        action_type="reply_only",
        intent="diagnostic",
        requires_execution=False,
        summary=summary or f"Support requested: {cmd_preview}",
        clarifying_questions=questions or [
            "若需從叢集內執行 nslookup/ping，請提供目標 Pod 的 namespace 與名稱，"
            "或於 config 設定 diagnostics.pods_exec。"
        ],
        source=source,
    )


def _validate_analysis_payload(
    payload: Dict[str, Any],
    *,
    comment_text: str,
    action_inference: ActionInference,
    allow_host_exec: bool = False,
) -> Optional[CommentAnalysis]:
    action_type = _normalize_action_type(str(payload.get("action_type", "no_action")))
    if action_type not in VALID_ACTION_TYPES:
        action_type = "no_action"

    mcp_calls = actions_from_payload(payload.get("mcp_calls", []))
    shell_commands = _shell_commands_from_payload(payload, comment_text)

    questions_raw = payload.get("clarifying_questions", [])
    if not isinstance(questions_raw, list):
        questions_raw = []
    questions = [str(q).strip() for q in questions_raw if str(q).strip()]

    actionable = bool(payload.get("actionable", False))
    requires_execution = bool(
        payload.get("requires_execution", action_type == "call_mcp")
    )
    summary = str(payload.get("summary", ""))

    if action_type == "call_mcp" and not mcp_calls and shell_commands:
        inferred = action_inference.infer_shell_diag_actions(shell_commands)
        if inferred:
            route = inferred[0].tool
            log_info(
                "shell_diag_inferred",
                commands=shell_commands,
                route=route,
                pods=[a.arguments.get("name") for a in inferred if a.tool == "pods_exec"],
            )
            return CommentAnalysis(
                actionable=True,
                action_type="call_mcp",
                mcp_calls=inferred,
                intent=str(payload.get("intent", "diagnostic")),
                requires_execution=True,
                summary=summary or f"Support requested shell diagnostics via {route}.",
                clarifying_questions=questions,
                source="llm+infer",
            )

        log_warning(
            "llm_returned_shell_commands",
            commands=shell_commands,
            hint="No pods_exec target or exec provider; falling back to reply_only",
        )
        return _reply_only_for_unmapped(
            summary=summary,
            questions=questions,
            shell_commands=shell_commands,
            source="llm",
            allow_host_exec=allow_host_exec,
        )

    if action_type == "call_mcp" and not mcp_calls:
        if questions:
            action_type = "clarify"
            requires_execution = False
            actionable = True
        else:
            actionable = False
            action_type = "no_action"

    if action_type == "no_action" and looks_like_explicit_support_request(comment_text):
        inferred = action_inference.infer_shell_diag_actions(shell_commands)
        if inferred:
            route = inferred[0].tool
            return CommentAnalysis(
                actionable=True,
                action_type="call_mcp",
                mcp_calls=inferred,
                intent="diagnostic",
                requires_execution=True,
                summary=summary or f"Explicit support request mapped to {route}.",
                source="infer",
            )
        return _reply_only_for_unmapped(
            summary=summary,
            questions=questions,
            shell_commands=shell_commands,
            source="llm",
            allow_host_exec=allow_host_exec,
        )

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


def _finalize_semantic_analysis(
    analysis: CommentAnalysis,
    *,
    comment_text: str,
    action_inference: ActionInference,
    allow_host_exec: bool,
    mcp_tool_names: Optional[List[str]] = None,
) -> CommentAnalysis:
    analysis = action_inference.apply_shell_diag_override(analysis, comment_text)
    return _apply_clarify_enrichment(
        analysis,
        comment_text,
        mcp_tool_names=mcp_tool_names or [],
        allow_host_exec=allow_host_exec,
    )
