from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from bridges.case_portal import CasePortalBridge
from core.case_convergence import CaseConvergenceAssessor
from core.collaboration_reasoner import CollaborationReasoner
from core.comment_analyzer import CommentAnalyzer, CommentAnalysis
from core.approval import (
    filter_unapproved_actions,
    register_pending_approvals,
)
from core.audit_trail import AuditTrail
from core.collection_flow import process_post_execute_collection
from core.diag_bundle import (
    build_bundle_content,
    build_upload_action,
    should_bundle_outputs,
    write_output_bundle,
)
from core.agent_settings import get_reply_prefix
from core.investigation import (
    serialize_actions as serialize_investigate_actions,
    should_continue_investigation,
)
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction, MCPExecutor
from core.mcp_policy import MCPPolicyChecker
from core.reply_grounding import build_grounded_fallback_reply
from core.collaboration_reply import (
    is_substantive_collaborative_reply,
    resolve_collaborative_reply,
)
from core.reply_composer import ReplyComposer, _ensure_prefix
from core.reply_guardrail import ReplyGuardrail
from core.result_interpreter import ResultInterpreter
from core.turn_context import mcp_results_for_compose

_EXECUTION_FAILURE_MARKERS = (
    "error",
    "failed",
    "no such host",
    "unable to connect",
    "connection refused",
    "timeout",
)


class AgentState(TypedDict, total=False):
    case_id: str
    status: str
    latest_msg: str
    comment_id: int
    case_history: str
    policy_passed: bool
    last_comment_id: int
    proposed_commands: List[str]
    mcp_actions: List[Dict[str, Any]]
    execution_results: List[str]
    policy_reason: str
    processed_comment_ids: List[int]
    processed_content_hashes: List[str]
    history_bootstrapped: bool
    last_agent_reply_at: Optional[str]
    replies_this_session: int
    turn_state: str
    last_command_hash: Optional[str]
    dry_run: bool
    action_type: str
    intent: str
    request_summary: str
    clarifying_questions: List[str]
    analysis_source: str
    analysis_prefilled: bool
    interpretation_findings: str
    interpretation_next_steps: List[str]
    convergence_reason: str
    solution_summary: str
    composed_reply: str
    reply_posted: bool
    dangerous_command_blocked: bool
    dangerous_command_matched: str
    blocked_commands: List[str]
    diag_bundle_uploaded: bool
    diag_bundle_filename: str
    diag_bundle_path: str
    diag_bundle_upload_result: str
    collection_uploaded: bool
    collection_upload_filename: str
    collection_upload_path: str
    collection_upload_result: str
    attachment_verified: bool
    attachment_verify_detail: str
    approval_required: bool
    approval_pending: List[Dict[str, Any]]
    investigate_step: int
    needs_more_evidence: bool
    follow_up_mcp_actions: List[Dict[str, Any]]
    all_mcp_actions: List[Dict[str, Any]]
    collaboration_customer_voice: str
    collaboration_source: str
    convergence_signal: str
    compose_skip_reason: str
    reply_skipped_reason: str


@dataclass
class WorkflowDeps:
    portal: CasePortalBridge
    executor: MCPExecutor
    policy: MCPPolicyChecker
    reply_guardrail: ReplyGuardrail
    analyzer: CommentAnalyzer
    interpreter: ResultInterpreter
    collaboration: CollaborationReasoner
    convergence: CaseConvergenceAssessor
    composer: ReplyComposer
    config: Dict[str, Any]
    audit: Optional[AuditTrail] = None


def _allow_dangerous_mention_in_reply(state: AgentState) -> bool:
    """Allow explaining blocked/failed diagnostics without posting runnable dangerous cmds."""
    if state.get("blocked_commands"):
        return True
    if state.get("dangerous_command_blocked"):
        return True
    if state.get("action_type") == "dangerous_command":
        return True
    if state.get("action_type") in ("reply_only", "clarify"):
        return True
    if state.get("action_type") == "approval_required":
        return True
    results = state.get("execution_results") or []
    if results:
        joined = "\n".join(str(item) for item in results).lower()
        if any(marker in joined for marker in _EXECUTION_FAILURE_MARKERS):
            return True
    return False


def _current_batch_actions(state: AgentState) -> List[MCPAction]:
    raw = state.get("mcp_actions", [])
    actions: List[MCPAction] = []
    for item in raw:
        if isinstance(item, MCPAction):
            actions.append(item)
        elif isinstance(item, dict):
            actions.append(
                MCPAction(
                    tool=str(item.get("tool", "")),
                    arguments=dict(item.get("arguments", {})),
                    label=str(item.get("label", "")),
                )
            )
    return [a for a in actions if a.tool]


def _actions_from_state(state: AgentState) -> List[MCPAction]:
    raw = state.get("all_mcp_actions") or state.get("mcp_actions", [])
    actions: List[MCPAction] = []
    for item in raw:
        if isinstance(item, MCPAction):
            actions.append(item)
        elif isinstance(item, dict):
            actions.append(
                MCPAction(
                    tool=str(item.get("tool", "")),
                    arguments=dict(item.get("arguments", {})),
                    label=str(item.get("label", "")),
                )
            )
    return [a for a in actions if a.tool]


def _analysis_from_state(state: AgentState) -> CommentAnalysis:
    return CommentAnalysis(
        actionable=True,
        action_type=state.get("action_type", "call_mcp"),
        mcp_calls=_actions_from_state(state),
        intent=state.get("intent", "unknown"),
        requires_execution=state.get("action_type") == "call_mcp",
        summary=state.get("request_summary", ""),
        clarifying_questions=state.get("clarifying_questions", []),
        source=state.get("analysis_source", "state"),
    )


def _serialize_actions(actions: List[MCPAction]) -> List[Dict[str, Any]]:
    return [
        {"tool": a.tool, "arguments": a.arguments, "label": a.label}
        for a in actions
    ]


def build_workflow(deps: WorkflowDeps):
    def analyze_node(state: AgentState) -> Dict[str, Any]:
        if state.get("analysis_prefilled"):
            log_info(
                "analyze_skipped",
                comment_id=state.get("comment_id"),
                reason="prefilled_by_poll_cycle",
                action_type=state.get("action_type"),
                analysis_source=state.get("analysis_source"),
            )
            return {}

        log_info("analyze_start", comment_id=state.get("comment_id"))

        analysis = deps.analyzer.analyze(
            state.get("latest_msg", ""),
            case_history=state.get("case_history", ""),
        )

        log_info(
            "analyze_done",
            action_type=analysis.action_type,
            mcp_tools=[a.tool for a in analysis.mcp_calls],
            intent=analysis.intent,
            source=analysis.source,
        )
        return {
            "action_type": analysis.action_type,
            "mcp_actions": _serialize_actions(analysis.mcp_calls),
            "all_mcp_actions": _serialize_actions(analysis.mcp_calls),
            "proposed_commands": analysis.commands,
            "intent": analysis.intent,
            "request_summary": analysis.summary,
            "clarifying_questions": analysis.clarifying_questions,
            "analysis_source": analysis.source,
            "blocked_commands": list(analysis.blocked_commands),
            "investigate_step": 0,
            "needs_more_evidence": False,
            "follow_up_mcp_actions": [],
        }

    def policy_node(state: AgentState) -> Dict[str, Any]:
        action_type = state.get("action_type", "no_action")
        actions = _current_batch_actions(state)
        latest_msg = state.get("latest_msg", "")
        blocked_commands = list(state.get("blocked_commands") or [])
        handling = deps.policy.dangerous_handling

        if handling == "reject_all":
            is_dangerous, matched = deps.policy.is_dangerous_command(latest_msg)
            if is_dangerous:
                log_warning(
                    "dangerous_command_blocked",
                    matched=matched,
                    comment_id=state.get("comment_id"),
                )
                return {
                    "policy_passed": False,
                    "policy_reason": (
                        f"安全政策攔截：指令 `{matched}` 屬於危險系統操作，"
                        "禁止執行。請提供其他非破壞性的診斷方式。"
                    ),
                    "dangerous_command_blocked": True,
                    "dangerous_command_matched": matched,
                    "action_type": "dangerous_command",
                    "blocked_commands": blocked_commands,
                }
        elif blocked_commands:
            log_info(
                "dangerous_command_partial_skip",
                blocked=blocked_commands,
                comment_id=state.get("comment_id"),
            )

        if action_type != "call_mcp" or not actions:
            if blocked_commands and action_type == "dangerous_command":
                matched = blocked_commands[0]
                return {
                    "policy_passed": False,
                    "policy_reason": (
                        f"安全政策攔截：指令 `{matched}` 屬於危險系統操作，"
                        "禁止執行。請提供其他非破壞性的診斷方式。"
                    ),
                    "dangerous_command_blocked": True,
                    "dangerous_command_matched": matched,
                    "action_type": "dangerous_command",
                    "blocked_commands": blocked_commands,
                }
            log_info("policy_skip", reason="no_mcp_execution", action_type=action_type)
            return {
                "policy_passed": True,
                "policy_reason": "No MCP actions to run.",
                "dangerous_command_blocked": False,
                "dangerous_command_matched": "",
                "blocked_commands": blocked_commands,
            }

        passed, reason = deps.policy.check_all(actions)
        if not passed:
            log_warning("policy_blocked", tools=[a.tool for a in actions], reason=reason)
            if deps.audit:
                deps.audit.record_policy(
                    comment_id=state.get("comment_id"),
                    passed=False,
                    reason=reason,
                    tools=[a.tool for a in actions],
                    dry_run=bool(state.get("dry_run")),
                )
            return {
                "policy_passed": False,
                "policy_reason": reason,
                "dangerous_command_blocked": False,
                "dangerous_command_matched": "",
                "blocked_commands": blocked_commands,
            }

        log_info("policy_passed", tools=[a.tool for a in actions])
        partial_reason = "Passed"
        if blocked_commands:
            skipped = ", ".join(blocked_commands)
            partial_reason = f"Passed (skipped dangerous: {skipped})"
        if deps.audit:
            deps.audit.record_policy(
                comment_id=state.get("comment_id"),
                passed=True,
                reason=partial_reason,
                tools=[a.tool for a in actions],
                dry_run=bool(state.get("dry_run")),
            )
        return {
            "policy_passed": True,
            "policy_reason": partial_reason,
            "dangerous_command_blocked": False,
            "dangerous_command_matched": "",
            "blocked_commands": blocked_commands,
        }

    def execute_node(state: AgentState) -> Dict[str, Any]:
        action_type = state.get("action_type", "no_action")
        actions = _current_batch_actions(state)
        dry_run = state.get("dry_run", False)
        investigate_step = int(state.get("investigate_step") or 0)

        if action_type != "call_mcp" or not actions:
            return {"execution_results": [], "status": "POLLING"}

        if not state.get("policy_passed", False):
            return {"execution_results": [], "status": "POLLING"}

        case_id = str(state.get("case_id", "")).strip()
        unapproved = filter_unapproved_actions(case_id, actions, deps.config)
        if unapproved:
            pending = register_pending_approvals(
                case_id,
                unapproved,
                comment_id=state.get("comment_id"),
            )
            log_info(
                "approval_required",
                comment_id=state.get("comment_id"),
                pending=[item.get("fingerprint") for item in pending],
            )
            if deps.audit:
                deps.audit.record(
                    "approval_required",
                    comment_id=state.get("comment_id"),
                    dry_run=bool(state.get("dry_run")),
                    pending=pending,
                )
            return {
                "execution_results": [],
                "approval_required": True,
                "approval_pending": pending,
                "action_type": "approval_required",
                "status": "POLLING",
            }

        if dry_run:
            log_info(
                "dry_run_mcp",
                tools=[a.tool for a in actions],
                investigate_step=investigate_step,
            )
            if deps.audit:
                for action in actions:
                    deps.audit.record_mcp_call(
                        action,
                        comment_id=state.get("comment_id"),
                        provider="dry-run",
                        actual_tool=action.tool,
                        result_preview=f"(dry-run) would call MCP {action.tool}",
                        dry_run=True,
                    )
            new_results = [
                f"(dry-run) would call MCP {a.tool}" for a in actions
            ]
        else:
            new_results = deps.executor.run_many(actions)

        prior_results = list(state.get("execution_results") or [])
        if investigate_step > 0:
            combined_results = prior_results + new_results
        else:
            combined_results = new_results

        current_batch = _serialize_actions(actions)
        if investigate_step > 0:
            all_actions = list(state.get("all_mcp_actions") or []) + current_batch
        else:
            all_actions = current_batch

        if investigate_step > 0:
            log_info(
                "investigate_execute_done",
                step=investigate_step,
                tools=[a.tool for a in actions],
            )

        return {
            "execution_results": combined_results,
            "all_mcp_actions": all_actions,
            "status": "POLLING",
        }

    def collection_node(state: AgentState) -> Dict[str, Any]:
        actions = _actions_from_state(state)
        results = state.get("execution_results", [])
        case_id = str(state.get("case_id", "")).strip()
        dry_run = state.get("dry_run", False)

        if dry_run:
            would_upload = any(
                a.tool in ("oc_adm_must_gather", "upload_attachment_rh_portal")
                for a in actions
            )
            if would_upload:
                log_info("dry_run_collection", tools=[a.tool for a in actions])
            return {
                "collection_uploaded": False,
                "collection_upload_filename": "",
                "collection_upload_path": "",
                "collection_upload_result": "(dry-run) collection follow-up skipped",
                "attachment_verified": False,
                "attachment_verify_detail": "",
            }

        if state.get("action_type") != "call_mcp" or not actions or not state.get("policy_passed", False):
            return {
                "collection_uploaded": False,
                "collection_upload_filename": "",
                "collection_upload_path": "",
                "collection_upload_result": "",
                "attachment_verified": False,
                "attachment_verify_detail": "",
            }

        outcome = process_post_execute_collection(
            portal=deps.portal,
            executor=deps.executor,
            policy=deps.policy,
            case_id=case_id,
            actions=actions,
            execution_results=results,
            dry_run=dry_run,
        )
        patch: Dict[str, Any] = {
            "collection_uploaded": outcome.get("collection_uploaded", False),
            "collection_upload_filename": outcome.get("collection_upload_filename", ""),
            "collection_upload_path": outcome.get("collection_upload_path", ""),
            "collection_upload_result": outcome.get("collection_upload_result", ""),
            "attachment_verified": outcome.get("attachment_verified", False),
            "attachment_verify_detail": outcome.get("attachment_verify_detail", ""),
        }
        if "execution_results" in outcome:
            patch["execution_results"] = outcome["execution_results"]
        return patch

    def bundle_node(state: AgentState) -> Dict[str, Any]:
        actions = _actions_from_state(state)
        results = state.get("execution_results", [])
        blocked_commands = list(state.get("blocked_commands") or [])
        case_id = str(state.get("case_id", "")).strip()

        if not should_bundle_outputs(
            config=deps.config,
            actions=actions,
            execution_results=results,
            blocked_commands=blocked_commands,
        ):
            return {
                "diag_bundle_uploaded": False,
                "diag_bundle_filename": "",
                "diag_bundle_path": "",
                "diag_bundle_upload_result": "",
            }

        content = build_bundle_content(
            case_id=case_id,
            actions=actions,
            execution_results=results,
            blocked_commands=blocked_commands,
            policy=deps.policy,
        )
        bundle_path = write_output_bundle(deps.config, content, case_id=case_id)
        filename = bundle_path.name
        log_info(
            "diag_bundle_written",
            path=str(bundle_path),
            bytes=len(content.encode("utf-8")),
        )

        if state.get("dry_run"):
            log_info("dry_run_diag_bundle_upload", path=str(bundle_path))
            return {
                "diag_bundle_uploaded": False,
                "diag_bundle_filename": filename,
                "diag_bundle_path": str(bundle_path),
                "diag_bundle_upload_result": f"(dry-run) would upload {bundle_path}",
            }

        if not case_id:
            return {
                "diag_bundle_uploaded": False,
                "diag_bundle_filename": filename,
                "diag_bundle_path": str(bundle_path),
                "diag_bundle_upload_result": "case_id missing; bundle written locally only",
            }

        upload_action = build_upload_action(case_id, bundle_path)
        passed, reason = deps.policy.check_action(upload_action)
        if not passed:
            log_warning("diag_bundle_upload_blocked", reason=reason)
            return {
                "diag_bundle_uploaded": False,
                "diag_bundle_filename": filename,
                "diag_bundle_path": str(bundle_path),
                "diag_bundle_upload_result": reason,
            }

        upload_result = deps.executor.run_action(upload_action)
        uploaded = "error" not in upload_result.lower()
        log_info(
            "diag_bundle_uploaded" if uploaded else "diag_bundle_upload_failed",
            filename=filename,
            case_id=case_id,
        )
        return {
            "diag_bundle_uploaded": uploaded,
            "diag_bundle_filename": filename,
            "diag_bundle_path": str(bundle_path),
            "diag_bundle_upload_result": upload_result,
        }

    def interpret_node(state: AgentState) -> Dict[str, Any]:
        actions = _actions_from_state(state)
        results = state.get("execution_results", [])
        action_labels = ", ".join(a.display_label() for a in actions) or "(none)"
        results_text = "\n---\n".join(results) if results else "(none)"
        investigate_step = int(state.get("investigate_step") or 0)

        interpretation = deps.interpreter.interpret(
            case_history=state.get("case_history", ""),
            request_summary=state.get("request_summary", ""),
            mcp_actions=action_labels,
            mcp_results=results_text,
            mcp_tool_names=getattr(deps.analyzer, "mcp_tool_names", []),
            investigate_step=investigate_step,
        )
        follow_up = interpretation.get("follow_up_mcp_calls") or []
        log_info(
            "interpret_done",
            confidence=interpretation.get("confidence"),
            source=interpretation.get("source"),
            needs_more_evidence=interpretation.get("needs_more_evidence"),
            follow_up_tools=[action.tool for action in follow_up],
            investigate_step=investigate_step,
        )
        return {
            "interpretation_findings": interpretation.get("findings", ""),
            "interpretation_next_steps": interpretation.get("next_steps", []),
            "needs_more_evidence": bool(interpretation.get("needs_more_evidence")),
            "follow_up_mcp_actions": serialize_investigate_actions(follow_up),
        }

    def investigate_prepare_node(state: AgentState) -> Dict[str, Any]:
        follow_up = list(state.get("follow_up_mcp_actions") or [])
        next_step = int(state.get("investigate_step") or 0) + 1
        log_info(
            "investigate_prepare",
            step=next_step,
            tools=[item.get("tool") for item in follow_up if isinstance(item, dict)],
        )
        if deps.audit:
            deps.audit.record(
                "investigate_follow_up",
                comment_id=state.get("comment_id"),
                dry_run=bool(state.get("dry_run")),
                investigate_step=next_step,
                tools=[item.get("tool") for item in follow_up if isinstance(item, dict)],
            )
        return {
            "mcp_actions": follow_up,
            "action_type": "call_mcp",
            "investigate_step": next_step,
            "needs_more_evidence": False,
            "follow_up_mcp_actions": [],
            "policy_passed": True,
            "policy_reason": "",
        }

    def collaborate_node(state: AgentState) -> Dict[str, Any]:
        action_type = state.get("action_type", "no_action")
        if action_type not in ("reply_only", "clarify"):
            return {}

        reasoning = deps.collaboration.reason(
            case_history=state.get("case_history", ""),
            request_summary=state.get("request_summary", ""),
            action_type=action_type,
            clarifying_questions=state.get("clarifying_questions", []),
            memory=state,
        )
        source = reasoning.get("source", "unknown")
        log_info(
            "collaborate_done",
            action_type=action_type,
            source=source,
            has_customer_voice=bool(reasoning.get("customer_voice")),
            convergence_signal=reasoning.get("convergence_signal"),
        )
        return {
            "interpretation_findings": reasoning.get("findings", ""),
            "interpretation_next_steps": reasoning.get("next_steps", []),
            "collaboration_customer_voice": reasoning.get("customer_voice", ""),
            "collaboration_source": source,
            "convergence_signal": reasoning.get("convergence_signal", "none"),
            "diagnosis_understanding": reasoning.get("diagnosis_understanding", ""),
            "confirmation_questions": reasoning.get("confirmation_questions", []),
            "customer_actions": reasoning.get("customer_actions", []),
            "verification_plan": reasoning.get("verification_plan", ""),
        }

    def convergence_node(state: AgentState) -> Dict[str, Any]:
        next_steps = state.get("interpretation_next_steps", [])
        assessment = deps.convergence.assess(
            case_history=state.get("case_history", ""),
            request_summary=state.get("request_summary", ""),
            interpretation_findings=state.get("interpretation_findings", ""),
            next_steps="\n".join(f"- {s}" for s in next_steps) if next_steps else "(none)",
        )
        status = assessment.get("case_status", "POLLING")
        return {
            "status": status,
            "convergence_reason": assessment.get("reason", ""),
            "solution_summary": assessment.get("solution_summary", ""),
        }

    def compose_node(state: AgentState) -> Dict[str, Any]:
        action_type = state.get("action_type", "no_action")
        mcp_actions = _actions_from_state(state)
        mcp_results = mcp_results_for_compose(
            action_type=action_type,
            mcp_actions=mcp_actions,
            mcp_results=state.get("execution_results", []),
        )
        reply_text = deps.composer.compose(
            case_history=state.get("case_history", ""),
            request_summary=state.get("request_summary", ""),
            action_type=action_type,
            mcp_actions=mcp_actions,
            mcp_results=mcp_results,
            policy_passed=state.get("policy_passed", True),
            policy_reason=state.get("policy_reason", ""),
            dangerous_command_matched=state.get("dangerous_command_matched", ""),
            blocked_commands=state.get("blocked_commands", []),
            policy_checker=deps.policy,
            diag_bundle_uploaded=bool(state.get("diag_bundle_uploaded")),
            diag_bundle_filename=state.get("diag_bundle_filename", ""),
            diag_bundle_upload_result=state.get("diag_bundle_upload_result", ""),
            collection_uploaded=bool(state.get("collection_uploaded")),
            collection_upload_filename=state.get("collection_upload_filename", ""),
            collection_upload_result=state.get("collection_upload_result", ""),
            attachment_verified=bool(state.get("attachment_verified")),
            attachment_verify_detail=state.get("attachment_verify_detail", ""),
            interpretation_findings=state.get("interpretation_findings", ""),
            next_steps=state.get("interpretation_next_steps", []),
            clarifying_questions=state.get("clarifying_questions", []),
            approval_pending=state.get("approval_pending", []),
            collaboration_draft=state.get("collaboration_customer_voice", ""),
        )
        compose_skip_reason = ""
        if not reply_text and action_type in ("reply_only", "clarify"):
            source = state.get("collaboration_source", "")
            if source == "unavailable":
                compose_skip_reason = "collaborate_llm_unavailable"
            elif not state.get("collaboration_customer_voice"):
                compose_skip_reason = "collaborate_no_substantive_voice"
            else:
                compose_skip_reason = "collaborate_echo_or_hollow"
            log_info("compose_skipped", reason=compose_skip_reason)
        if reply_text and state.get("solution_summary"):
            reply_text = (
                f"{reply_text.rstrip()}\n\n"
                f"（問題收斂摘要：{state['solution_summary']}）"
            )
        convergence_reason = (state.get("convergence_reason") or "").strip()
        if reply_text and convergence_reason and state.get("status") == "RESOLVED":
            reply_text = (
                f"{reply_text.rstrip()}\n\n"
                f"（收斂判定：{convergence_reason}）"
            )
        if reply_text:
            log_info("compose_done", reply_preview=reply_text[:120])
        elif not compose_skip_reason:
            log_info("compose_skipped", reason="no_substantive_reply")
        return {
            "composed_reply": reply_text or "",
            "compose_skip_reason": compose_skip_reason,
        }

    def post_node(state: AgentState) -> Dict[str, Any]:
        case_id = state.get("case_id", "unknown")
        dry_run = state.get("dry_run", False)
        reply_text = state.get("composed_reply", "")

        if not reply_text or not reply_text.strip():
            skip_reason = state.get("compose_skip_reason") or "no_substantive_content"
            log_info("reply_not_posted", reason=skip_reason)
            return {
                "reply_posted": False,
                "status": state.get("status", "POLLING"),
                "reply_skipped_reason": skip_reason,
            }

        if dry_run:
            log_info("dry_run_reply", reply_preview=reply_text[:200])
            return {"reply_posted": False, "status": state.get("status", "POLLING")}

        allow_dangerous_mention = _allow_dangerous_mention_in_reply(state)
        passed, guard_reason, safe_text = deps.reply_guardrail.validate(
            reply_text,
            allow_dangerous_mention=allow_dangerous_mention,
            action_type=state.get("action_type", ""),
            execution_results=state.get("execution_results", []),
            request_summary=state.get("request_summary", ""),
            dry_run=dry_run,
        )
        if not passed and guard_reason == "echo_of_support_message":
            draft = resolve_collaborative_reply(
                customer_voice=state.get("collaboration_customer_voice", ""),
                findings=state.get("interpretation_findings", ""),
                request_summary=state.get("request_summary", ""),
            )
            if draft and is_substantive_collaborative_reply(draft):
                passed, guard_reason, safe_text = deps.reply_guardrail.validate(
                    _ensure_prefix(draft),
                    allow_dangerous_mention=allow_dangerous_mention,
                    action_type=state.get("action_type", ""),
                    execution_results=[],
                    request_summary=state.get("request_summary", ""),
                    dry_run=dry_run,
                    skip_grounding=True,
                )
                if passed:
                    log_warning(
                        "reply_echo_rescue",
                        comment_id=state.get("comment_id"),
                    )
        if not passed and guard_reason.startswith("ungrounded_execution_output"):
            fallback = build_grounded_fallback_reply(
                reply_prefix=get_reply_prefix(),
                request_summary=state.get("request_summary", ""),
                mcp_actions=_actions_from_state(state),
                execution_results=state.get("execution_results", []),
            )
            log_warning(
                "reply_grounding_fallback",
                reason=guard_reason,
                comment_id=state.get("comment_id"),
            )
            passed, guard_reason, safe_text = deps.reply_guardrail.validate(
                fallback,
                allow_dangerous_mention=True,
                action_type=state.get("action_type", ""),
                execution_results=state.get("execution_results", []),
                request_summary=state.get("request_summary", ""),
                dry_run=dry_run,
                skip_grounding=True,
            )
        if not passed:
            log_warning(
                "reply_guardrail_blocked",
                reason=guard_reason,
                comment_id=state.get("comment_id"),
            )
            return {
                "reply_posted": False,
                "status": state.get("status", "POLLING"),
                "reply_skipped_reason": guard_reason,
            }
        if guard_reason == "truncated":
            log_warning(
                "reply_guardrail_truncated",
                max_chars=deps.reply_guardrail.max_chars,
                comment_id=state.get("comment_id"),
            )

        post_result = deps.portal.add_comment(case_id, safe_text)
        return {
            "reply_posted": post_result.get("success", False),
            "status": state.get("status", "POLLING"),
        }

    workflow = StateGraph(AgentState)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("policy", policy_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("collection", collection_node)
    workflow.add_node("bundle", bundle_node)
    workflow.add_node("interpret", interpret_node)
    workflow.add_node("investigate_prepare", investigate_prepare_node)
    workflow.add_node("collaborate", collaborate_node)
    workflow.add_node("convergence", convergence_node)
    workflow.add_node("compose", compose_node)
    workflow.add_node("post", post_node)
    def _route_after_policy(state: AgentState) -> str:
        if state.get("dangerous_command_blocked"):
            return "compose"
        action_type = state.get("action_type", "no_action")
        if action_type == "call_mcp" and state.get("policy_passed", True):
            return "execute"
        if action_type == "call_mcp" and not state.get("policy_passed", True):
            if int(state.get("investigate_step") or 0) > 0:
                log_info(
                    "investigate_policy_blocked",
                    reason=state.get("policy_reason", ""),
                    investigate_step=state.get("investigate_step"),
                )
                return "collection"
            log_info("policy_short_circuit", reason="mcp_blocked_skip_execute")
            return "compose"
        if action_type in ("reply_only", "clarify"):
            return "collaborate"
        if action_type in ("no_action", "dangerous_command", "approval_required"):
            return "compose"
        return "execute"

    def _route_after_execute(state: AgentState) -> str:
        if state.get("approval_required"):
            return "compose"
        return "interpret"

    def _route_after_interpret(state: AgentState) -> str:
        if should_continue_investigation(state, deps.config):
            return "investigate_prepare"
        return "collection"

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "policy")
    workflow.add_conditional_edges("policy", _route_after_policy, {"execute": "execute", "compose": "compose", "collection": "collection", "collaborate": "collaborate"})
    workflow.add_edge("collaborate", "convergence")
    workflow.add_conditional_edges(
        "execute",
        _route_after_execute,
        {"compose": "compose", "interpret": "interpret"},
    )
    workflow.add_conditional_edges(
        "interpret",
        _route_after_interpret,
        {"investigate_prepare": "investigate_prepare", "collection": "collection"},
    )
    workflow.add_edge("investigate_prepare", "policy")
    workflow.add_edge("collection", "bundle")
    workflow.add_edge("bundle", "convergence")
    workflow.add_edge("convergence", "compose")
    workflow.add_edge("compose", "post")
    workflow.add_edge("post", END)
    return workflow.compile()
