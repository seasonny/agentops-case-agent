from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.comments import normalize_comment_text
from core.config import ANALYZE_PROMPT_FILE
from core.agent_settings import get_reply_prefix
from core.llm_client import chat_json, is_llm_available
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction, build_tools_catalog
from core.cluster_read_routing import (
    infer_cluster_read_actions_from_text,
    is_cluster_read_only_request,
)
from core.clarify_templates import (
    enrich_clarifying_questions,
    should_use_clarify_instead_of_reply_only,
)
from core.collection_flow import (
    infer_explicit_upload_analysis,
    infer_must_gather_analysis,
)
from core.dangerous_command_split import split_comment_requests
from core.mcp_policy import MCPPolicyChecker, actions_from_payload
from core.shell_diagnostics import (
    extract_shell_commands_from_text,
    infer_shell_diag_actions,
    is_shell_only_request,
    looks_like_explicit_support_request,
    needs_shell_diag_routing_override,
)

VALID_ACTION_TYPES = frozenset({
    "call_mcp",
    "execute_commands",
    "reply_only",
    "clarify",
    "no_action",
    "dangerous_command",
})


@dataclass
class CommentAnalysis:
    actionable: bool = False
    action_type: str = "no_action"
    mcp_calls: List[MCPAction] = field(default_factory=list)
    intent: str = "unknown"
    requires_execution: bool = False
    summary: str = ""
    clarifying_questions: List[str] = field(default_factory=list)
    blocked_commands: List[str] = field(default_factory=list)
    source: str = "none"

    @property
    def commands(self) -> List[str]:
        return [action.display_label() for action in self.mcp_calls]

    def is_processable(self) -> bool:
        if self.action_type == "dangerous_command":
            return True
        if not self.actionable or self.action_type == "no_action":
            return False
        if self.action_type in ("call_mcp", "execute_commands"):
            return bool(self.mcp_calls)
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actionable": self.actionable,
            "action_type": self.action_type,
            "mcp_calls": [
                {"tool": a.tool, "arguments": a.arguments, "label": a.label}
                for a in self.mcp_calls
            ],
            "intent": self.intent,
            "requires_execution": self.requires_execution,
            "summary": self.summary,
            "clarifying_questions": self.clarifying_questions,
            "blocked_commands": list(self.blocked_commands),
            "source": self.source,
        }


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


def _load_analyze_template() -> str:
    if ANALYZE_PROMPT_FILE.exists():
        return ANALYZE_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Analyze comment with case history. JSON only. "
        "Latest: {comment_text} History: {case_history}"
    )


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


def _deterministic_collection_analysis(
    comment_text: str,
    *,
    case_id: str,
    mcp_tool_names: List[str],
    policy: MCPPolicyChecker,
) -> Optional[CommentAnalysis]:
    upload = infer_explicit_upload_analysis(
        comment_text,
        case_id,
        mcp_tool_names=mcp_tool_names,
        policy=policy,
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
        mcp_tool_names=mcp_tool_names,
        policy=policy,
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


def _apply_shell_diag_routing_override(
    analysis: CommentAnalysis,
    *,
    comment_text: str,
    config: Dict[str, Any],
    allow_host_exec: bool,
) -> CommentAnalysis:
    if analysis.action_type != "call_mcp":
        return analysis
    if not needs_shell_diag_routing_override(analysis.mcp_calls, comment_text):
        return analysis

    shell_commands = extract_shell_commands_from_text(comment_text)
    inferred = infer_shell_diag_actions(
        shell_commands,
        config,
        allow_host_exec=allow_host_exec,
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
    source = analysis.source if analysis.source.endswith("+route") else f"{analysis.source}+route"
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


def _deterministic_cluster_read_analysis(comment_text: str) -> Optional[CommentAnalysis]:
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


def _deterministic_shell_diag_analysis(
    comment_text: str,
    config: Dict[str, Any],
    *,
    allow_host_exec: bool,
) -> Optional[CommentAnalysis]:
    if not is_shell_only_request(comment_text):
        return None
    shell_commands = extract_shell_commands_from_text(comment_text)
    inferred = infer_shell_diag_actions(
        shell_commands,
        config,
        allow_host_exec=allow_host_exec,
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


def _validate_analysis_payload(
    payload: Dict[str, Any],
    *,
    comment_text: str,
    config: Dict[str, Any],
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
        inferred = infer_shell_diag_actions(
            shell_commands,
            config,
            allow_host_exec=allow_host_exec,
        )
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
        inferred = infer_shell_diag_actions(
            shell_commands,
            config,
            allow_host_exec=allow_host_exec,
        )
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


def _finalize_analysis(
    analysis: CommentAnalysis,
    *,
    comment_text: str,
    config: Dict[str, Any],
    allow_host_exec: bool,
    mcp_tool_names: Optional[List[str]] = None,
) -> CommentAnalysis:
    analysis = _apply_shell_diag_routing_override(
        analysis,
        comment_text=comment_text,
        config=config,
        allow_host_exec=allow_host_exec,
    )
    return _apply_clarify_enrichment(
        analysis,
        comment_text,
        mcp_tool_names=mcp_tool_names or [],
        allow_host_exec=allow_host_exec,
    )


def _collaboration_reply_analysis(text: str, *, source: str) -> CommentAnalysis:
    """Support informational / solution discussion — no MCP, but customer should respond."""
    normalized = normalize_comment_text(text)
    return CommentAnalysis(
        actionable=True,
        action_type="reply_only",
        intent="solution_discussion",
        summary=normalized[:500] if normalized else "Support update",
        source=source,
    )


def _without_llm_analysis(
    text: str,
    config: Dict[str, Any],
    *,
    allow_host_exec: bool = False,
) -> CommentAnalysis:
    normalized = normalize_comment_text(text)
    if get_reply_prefix() in normalized:
        return CommentAnalysis(actionable=False, action_type="no_action", source="unavailable")

    if looks_like_explicit_support_request(normalized):
        shell_commands = extract_shell_commands_from_text(normalized)
        inferred = infer_shell_diag_actions(
            shell_commands,
            config,
            allow_host_exec=allow_host_exec,
        )
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
        return _collaboration_reply_analysis(normalized, source="unavailable")

    return CommentAnalysis(
        actionable=False,
        action_type="no_action",
        summary="LLM 未設定，無法進行語意 triage。",
        source="unavailable",
    )


def _render_prompt(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


class CommentAnalyzer:
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
    ) -> CommentAnalysis:
        if not normalize_comment_text(comment_text):
            return CommentAnalysis(actionable=False, action_type="no_action", source="none")

        blocked_early, working_text, blocked_commands = self._evaluate_dangerous_split(
            comment_text
        )
        if blocked_early is not None:
            return blocked_early

        routed = _deterministic_cluster_read_analysis(working_text)
        if routed is not None:
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

        routed = _deterministic_shell_diag_analysis(
            working_text,
            self.config,
            allow_host_exec=self.allow_host_exec,
        )
        if routed is not None:
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

        case_id = str(self.config.get("case_id", "") or "").strip()
        routed = _deterministic_collection_analysis(
            working_text,
            case_id=case_id,
            mcp_tool_names=self.mcp_tool_names,
            policy=self.policy,
        )
        if routed is not None:
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

        if not is_llm_available(self.llm_config):
            result = _without_llm_analysis(
                working_text,
                self.config,
                allow_host_exec=self.allow_host_exec,
            )
            result = _filter_dangerous_mcp_calls(result, self.policy)
            return _attach_blocked_commands(result, blocked_commands)

        llm_result = self._analyze_with_llm(
            working_text,
            case_history,
            comment_author=comment_author,
            resolved_role=resolved_role,
            trigger_reason=trigger_reason,
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
            cluster_inferred = infer_cluster_read_actions_from_text(working_text)
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
            inferred = infer_shell_diag_actions(
                shell_commands,
                self.config,
                allow_host_exec=self.allow_host_exec,
            )
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
                _collaboration_reply_analysis(working_text, source="infer"),
                blocked_commands,
            )

        log_warning("llm_triage_failed", fallback="no_action")
        return CommentAnalysis(
            actionable=False,
            action_type="no_action",
            summary="LLM triage 失敗，略過此留言。",
            source="unavailable",
        )

    def _analyze_with_llm(
        self,
        comment_text: str,
        case_history: str,
        *,
        comment_author: str = "",
        resolved_role: str = "",
        trigger_reason: str = "",
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
        payload = chat_json(
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
            config=self.config,
            allow_host_exec=self.allow_host_exec,
        )
        if analysis is None:
            return None
        return _finalize_analysis(
            analysis,
            comment_text=comment_text,
            config=self.config,
            allow_host_exec=self.allow_host_exec,
            mcp_tool_names=self.mcp_tool_names,
        )
