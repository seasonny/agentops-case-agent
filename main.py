#!/usr/bin/env python3
"""AgentOps Case Agent — CLI entry point."""

import argparse
import hashlib
import time
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

warnings.filterwarnings("ignore")

from bridges.case_portal import CasePortalBridge
from bridges.mcp_registry import MCPRegistry
from core.case_context import build_case_history
from core.comment_analyzer import CommentAnalyzer
from core.comments import (
    collect_support_candidates,
    commands_hash,
    is_agent_reply,
    is_automated_support_boilerplate,
    is_comment_handled,
    is_in_cooldown,
    normalize_comment_text,
    session_limit_reached,
    sort_comments_chronologically,
)
from core.agent_settings import get_loop_guard_seconds, init_agent_settings
from core.config import iter_mcp_provider_specs, load_config
from core.policy_compiler import load_compiled_policy, policy_to_dict
from core.setup_check import run_setup_check
from core.constants import TURN_OWNER_CUSTOMER, TURN_PROCESSING, TURN_WAITING
from core.case_convergence import CaseConvergenceAssessor
from core.llm_client import require_llm
from core.logging import log_info, log_warning
from core.participants import ParticipantResolver
from core.mcp_action import MCPExecutor
from core.mcp_policy import MCPPolicyChecker
from core.trigger import TriggerConfig
from core.memory import (
    bootstrap_comment_history,
    load_agent_memory,
    mark_comment_handled,
    maybe_unmark_failed_execution,
    migrate_handled_keys_from_legacy,
    record_agent_reply,
    reset_agent_memory,
    save_agent_memory,
)
from core.reply_composer import ReplyComposer
from core.reply_guardrail import ReplyGuardrail
from core.audit_trail import AuditTrail, format_audit_report_text
from core.approval import approve_fingerprint, format_pending_approvals_text
from core.case_context_memory import augment_case_history, record_diagnostics, record_hypothesis
from core.outage import notify_webhook, poll_interval_seconds
from core.poc_metrics import format_report_text, summarize_metrics
from core.run_report import format_run_summary_human, persist_run_report
from core.collaboration_reasoner import CollaborationReasoner
from core.result_interpreter import ResultInterpreter
from core.turn_context import reset_turn_execution_state
from workflow.graph import WorkflowDeps, build_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgentOps Case Agent")
    parser.add_argument("--case-id", help="Override case ID from config or CASE_ID env")
    parser.add_argument("--reset-memory", action="store_true", help="Reset agent memory before start")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only; do not execute or reply")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run setup checks (LLM, MCP, Case read) and exit",
    )
    parser.add_argument(
        "--policy-dump",
        action="store_true",
        help="Print compiled security policy as JSON and exit",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print PoC metrics summary for the case and exit",
    )
    parser.add_argument(
        "--report-json",
        action="store_true",
        help="Print PoC metrics summary as JSON and exit",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Print health check summary and exit",
    )
    parser.add_argument(
        "--health-json",
        action="store_true",
        help="Print health check as JSON and exit",
    )
    parser.add_argument(
        "--audit-report",
        action="store_true",
        help="Print audit trail summary for the case and exit",
    )
    parser.add_argument(
        "--pending-approvals",
        action="store_true",
        help="List pending human approvals for the case and exit",
    )
    parser.add_argument(
        "--approve",
        metavar="FINGERPRINT",
        help="Approve a pending MCP action by fingerprint",
    )
    parser.add_argument(
        "--approved-by",
        default="operator",
        help="Name recorded when using --approve",
    )
    return parser.parse_args()


# Reasons that should NOT permanently mark a comment as handled (allow retry).
_RETRIABLE_SKIP_REASONS = frozenset({
    "not_actionable",
    "no_mcp_actions",
    "llm_unavailable",
    "not_processable",
})

_STICKY_BLOCKER_MARKERS = (
    "no such host",
    "unable to connect to the server",
    "failed to list pods in all namespaces",
    "missing argument name",
    "mcp server not available",
    "mcp server not started",
)


def _extract_blocker_signature(results: List[str]) -> str:
    lowered = "\n".join((r or "").lower() for r in results if isinstance(r, str))
    hits = [marker for marker in _STICKY_BLOCKER_MARKERS if marker in lowered]
    if not hits:
        return ""
    return hashlib.sha256("|".join(sorted(set(hits))).encode("utf-8")).hexdigest()


def _seconds_since_last_reply(memory: Dict[str, Any]) -> float:
    raw = memory.get("last_agent_reply_at")
    if not raw:
        return 10**9
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return 10**9
    return (datetime.now(timezone.utc) - dt).total_seconds()


def _should_skip_looping_request(memory: Dict[str, Any], analysis) -> bool:
    if analysis.action_type not in ("call_mcp", "execute_commands"):
        return False
    if not analysis.commands:
        return False
    current_hash = commands_hash(analysis.commands)
    if current_hash != memory.get("last_command_hash"):
        return False
    if not memory.get("last_blocker_signature"):
        return False
    # Prevent rapid no-value loops in one-person demo mode.
    return _seconds_since_last_reply(memory) < get_loop_guard_seconds()


def skip_and_mark(
    memory: Dict[str, Any],
    comment: Dict[str, Any],
    processed_ids: Set[int],
    processed_keys: Set[str],
    reason: str,
) -> None:
    log_info("comment_skipped", comment_id=comment["id"], reason=reason)
    mark_comment_handled(memory, comment, processed_ids, processed_keys)


def process_poll_cycle(
    memory: Dict[str, Any],
    config: Dict[str, Any],
    portal: CasePortalBridge,
    app,
    analyzer: CommentAnalyzer,
    resolver: ParticipantResolver,
    trigger_cfg: TriggerConfig,
    deps: WorkflowDeps,
    *,
    dry_run: bool,
) -> None:
    polling = config.get("polling", {})
    limits = config.get("limits", {})
    interval = poll_interval_seconds(config)
    cooldown = polling.get("cooldown_after_reply_seconds", 45)
    max_replies = limits.get("max_replies_per_session", 20)
    audit = AuditTrail(config=config, case_id=memory["case_id"])
    deps.audit = audit

    log_info(
        "poll_start",
        case_id=memory["case_id"],
        turn_state=memory.get("turn_state"),
        turn_owner=memory.get("turn_owner"),
        trigger_mode=trigger_cfg.mode,
    )

    if is_in_cooldown(memory, cooldown):
        remaining = memory.get("_cooldown_seconds_remaining", cooldown)
        log_info("cooldown_active", seconds_remaining=remaining)
        time.sleep(interval)
        return

    if session_limit_reached(memory, max_replies):
        log_warning("session_limit_reached", max_replies=max_replies)
        time.sleep(interval)
        return

    comments = portal.query_case_comments(memory["case_id"])
    if comments is None:
        log_warning("comments_unavailable")
        time.sleep(interval)
        return

    comments = resolver.enrich_comments(comments)

    processed_ids: Set[int] = set(memory.get("processed_comment_ids", []))
    processed_keys: Set[str] = set(memory.get("processed_handled_keys", []))

    maybe_unmark_failed_execution(memory, comments)
    processed_ids = set(memory.get("processed_comment_ids", []))
    processed_keys = set(memory.get("processed_handled_keys", processed_keys))
    migrate_handled_keys_from_legacy(memory, comments, processed_keys)
    bootstrap_comment_history(
        memory,
        comments,
        processed_keys,
        resolver=resolver,
        trigger_cfg=trigger_cfg,
    )

    case_history = augment_case_history(build_case_history(comments), memory)
    sorted_comments = sort_comments_chronologically(comments)

    for comment in sorted_comments:
        if is_comment_handled(comment, processed_keys):
            continue
        if is_agent_reply(comment):
            skip_and_mark(memory, comment, processed_ids, processed_keys, "agent_reply")
            continue
        if is_automated_support_boilerplate(comment):
            skip_and_mark(memory, comment, processed_ids, processed_keys, "automated_support")
            continue
        if trigger_cfg.ignore_customer_comments:
            role = comment.get("resolved_role", "customer")
            if role == "customer":
                skip_and_mark(memory, comment, processed_ids, processed_keys, "customer_internal")
                continue
        elif trigger_cfg.mode == "demo":
            role = comment.get("resolved_role", "customer")
            if role == "customer":
                eligible, reason = trigger_cfg.is_eligible(comment, role)
                if not eligible and reason == "customer_no_explicit_request":
                    skip_and_mark(
                        memory,
                        comment,
                        processed_ids,
                        processed_keys,
                        "customer_no_explicit_request",
                    )
                    continue

    analysis_cache: Dict[int, Any] = {}

    def analyze_comment(comment: Dict[str, Any]):
        comment_id = comment["id"]
        if comment_id in analysis_cache:
            return analysis_cache[comment_id]
        analysis = analyzer.analyze(
            comment.get("content", ""),
            case_history=case_history,
            comment_author=str(comment.get("author", "")),
            resolved_role=str(comment.get("resolved_role", "")),
            trigger_reason=str(comment.get("_trigger_reason", "")),
        )
        analysis_cache[comment_id] = analysis
        return analysis

    support_candidates, skipped_comments = collect_support_candidates(
        comments,
        processed_keys,
        analyze_fn=analyze_comment,
        resolver=resolver,
        trigger_cfg=trigger_cfg,
    )

    for comment, reason in skipped_comments:
        if reason in _RETRIABLE_SKIP_REASONS:
            log_info(
                "comment_deferred",
                comment_id=comment["id"],
                reason=reason,
                hint=(
                    "LLM 未就緒（請確認 GEMINI_API_KEY / OPENAI_API_KEY 與 provider 套件）"
                    if reason == "llm_unavailable"
                    else None
                ),
            )
            continue
        if reason == "historical_superseded":
            log_info("comment_superseded", comment_id=comment["id"])
        skip_and_mark(memory, comment, processed_ids, processed_keys, reason)

    if not support_candidates:
        log_info("no_new_support_requests")
    else:
        comment = support_candidates[-1]
        analysis = comment.get("_analysis") or analyzer.analyze(
            comment.get("content", ""),
            case_history=case_history,
            comment_author=str(comment.get("author", "")),
            resolved_role=str(comment.get("resolved_role", "")),
            trigger_reason=str(comment.get("_trigger_reason", "")),
        )
        if _should_skip_looping_request(memory, analysis):
            log_info(
                "comment_skipped_loop_guard",
                comment_id=comment["id"],
                reason="same_command_with_same_sticky_blocker",
                request_preview=normalize_comment_text(comment.get("content", ""))[:120],
            )
            skip_and_mark(
                memory,
                comment,
                processed_ids,
                processed_keys,
                "loop_guard_same_request_blocker",
            )
            memory["turn_state"] = memory.get("turn_state", TURN_WAITING)
            memory["processed_comment_ids"] = sorted(processed_ids)
            memory["processed_handled_keys"] = sorted(processed_keys)
            save_agent_memory(memory)
            time.sleep(interval)
            return

        memory["latest_msg"] = comment["content"]
        memory["comment_id"] = comment["id"]
        memory["case_history"] = case_history
        memory["status"] = TURN_PROCESSING
        memory["turn_state"] = TURN_PROCESSING
        memory["turn_owner"] = TURN_OWNER_CUSTOMER
        memory["dry_run"] = dry_run
        memory["action_type"] = analysis.action_type
        memory["mcp_actions"] = [
            {"tool": a.tool, "arguments": a.arguments, "label": a.label}
            for a in analysis.mcp_calls
        ]
        reset_turn_execution_state(
            memory,
            action_type=analysis.action_type,
            mcp_actions=analysis.mcp_calls,
        )
        memory["proposed_commands"] = analysis.commands
        memory["intent"] = analysis.intent
        memory["request_summary"] = analysis.summary
        memory["clarifying_questions"] = analysis.clarifying_questions
        memory["blocked_commands"] = list(analysis.blocked_commands)
        memory["analysis_source"] = analysis.source
        memory["analysis_prefilled"] = True

        run_started_at = datetime.now(timezone.utc)

        log_info(
            "processing_support_request",
            comment_id=comment["id"],
            comment_timestamp=comment.get("timestamp"),
            author=comment.get("author"),
            resolved_role=comment.get("resolved_role"),
            trigger_reason=comment.get("_trigger_reason"),
            request_preview=normalize_comment_text(comment.get("content", ""))[:120],
            action_type=analysis.action_type,
            dry_run=dry_run,
        )

        deps.executor.comment_id = comment["id"]
        deps.executor.dry_run = dry_run
        deps.executor.audit = audit

        output = app.invoke(memory)
        memory.update(output)
        memory["diagnostics_history"] = memory.get("diagnostics_history", [])
        memory["last_blocker_signature"] = _extract_blocker_signature(
            output.get("execution_results", [])
        )

        if (
            not output.get("approval_required")
            and output.get("action_type") == "call_mcp"
            and output.get("execution_results")
        ):
            from core.mcp_action import MCPAction as _MCPAction

            actions = [
                _MCPAction(
                    tool=str(item.get("tool", "")),
                    arguments=dict(item.get("arguments", {})),
                    label=str(item.get("label", "")),
                )
                for item in (output.get("all_mcp_actions") or output.get("mcp_actions") or [])
                if isinstance(item, dict)
            ]
            record_diagnostics(
                memory,
                actions,
                comment_id=comment["id"],
                config=config,
                execution_results=output.get("execution_results") or [],
            )

        if output.get("action_type") in ("reply_only", "clarify"):
            record_hypothesis(
                memory,
                comment_id=comment["id"],
                request_summary=output.get("request_summary") or analysis.summary,
                diagnosis_understanding=output.get("diagnosis_understanding", ""),
                customer_actions=output.get("customer_actions"),
                confirmation_questions=output.get("confirmation_questions"),
                verification_plan=output.get("verification_plan", ""),
                convergence_signal=output.get("convergence_signal", "none"),
                customer_voice=output.get("collaboration_customer_voice", ""),
            )

        run_record = persist_run_report(
            case_id=memory["case_id"],
            comment=comment,
            analysis=analysis,
            output=memory,
            dry_run=dry_run,
            started_at=run_started_at,
        )
        log_info(
            "run_report_saved",
            comment_id=comment["id"],
            action_type=run_record.get("action_type"),
            policy_passed=run_record.get("policy_passed"),
            reply_posted=run_record.get("reply_posted"),
            dry_run=dry_run,
        )
        if dry_run:
            print(format_run_summary_human(run_record))

        reply_posted = output.get("reply_posted", False)
        commands = output.get("proposed_commands", [])
        approval_required = bool(output.get("approval_required"))

        if approval_required:
            notify_webhook(
                config,
                "approval_required",
                case_id=memory["case_id"],
                message="MCP action awaiting human approval",
                fields={"comment_id": comment["id"]},
            )
            audit.record(
                "approval_waiting",
                comment_id=comment["id"],
                dry_run=dry_run,
                pending=output.get("approval_pending", []),
            )
        elif output.get("action_type") == "clarify":
            notify_webhook(
                config,
                "clarify",
                case_id=memory["case_id"],
                message="Agent posted clarify questions",
                fields={"comment_id": comment["id"]},
            )

        if dry_run:
            log_info(
                "dry_run_complete",
                comment_id=comment["id"],
                action_type=analysis.action_type,
                commands=commands,
            )
            mark_comment_handled(
                memory, comment, processed_ids, processed_keys, as_support=False
            )
        elif approval_required:
            if reply_posted:
                audit.record_reply(
                    comment_id=comment["id"],
                    posted=True,
                    action_type="approval_required",
                    dry_run=False,
                )
            log_warning(
                "approval_required_keep_pending",
                comment_id=comment["id"],
            )
        elif reply_posted:
            mark_comment_handled(
                memory, comment, processed_ids, processed_keys, as_support=True
            )
            record_agent_reply(memory, commands_hash(commands) if commands else None)
            audit.record_reply(
                comment_id=comment["id"],
                posted=True,
                action_type=output.get("action_type", analysis.action_type),
                dry_run=False,
            )
            notify_webhook(
                config,
                "reply_posted",
                case_id=memory["case_id"],
                message="Agent replied to Support",
                fields={"comment_id": comment["id"]},
            )
        else:
            if not output.get("policy_passed", True):
                notify_webhook(
                    config,
                    "policy_blocked",
                    case_id=memory["case_id"],
                    message=output.get("policy_reason", "policy blocked"),
                    fields={"comment_id": comment["id"]},
                )
            log_warning(
                "reply_failed_keep_pending",
                comment_id=comment["id"],
            )

    for comment in sorted_comments:
        if is_comment_handled(comment, processed_keys):
            continue
        if is_agent_reply(comment):
            skip_and_mark(memory, comment, processed_ids, processed_keys, "agent_reply_backfill")

    memory["processed_comment_ids"] = sorted(processed_ids)
    memory["processed_handled_keys"] = sorted(processed_keys)
    memory["history_bootstrapped"] = memory.get("history_bootstrapped", False)
    if processed_ids:
        memory["last_comment_id"] = max(processed_ids)
    memory["turn_state"] = memory.get("turn_state", TURN_WAITING)
    save_agent_memory(memory)

    time.sleep(interval)


def main() -> None:
    args = parse_args()
    config = load_config()
    init_agent_settings(config)
    case_id = args.case_id or config.get("case_id", "").strip()

    if args.policy_dump:
        import json as _json

        print(_json.dumps(policy_to_dict(load_compiled_policy()), indent=2, ensure_ascii=False))
        raise SystemExit(0)

    if args.check:
        raise SystemExit(run_setup_check(config, case_id=case_id))

    if args.report or args.report_json:
        if not case_id:
            log_warning("case_id_missing", hint="Set case_id in config/agent_config.json or CASE_ID env")
            raise SystemExit(1)
        if args.report_json:
            import json as _json

            print(_json.dumps(summarize_metrics(case_id), indent=2, ensure_ascii=False))
        else:
            print(format_report_text(case_id))
        raise SystemExit(0)

    if args.health or args.health_json:
        report = build_health_report(config, case_id=case_id)
        if args.health_json:
            import json as _json

            print(_json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_health_text(report))
        raise SystemExit(0 if report.get("status") == "healthy" else 1)

    if args.audit_report:
        if not case_id:
            log_warning("case_id_missing", hint="Set case_id in config/agent_config.json or CASE_ID env")
            raise SystemExit(1)
        print(format_audit_report_text(case_id))
        raise SystemExit(0)

    if args.pending_approvals:
        if not case_id:
            log_warning("case_id_missing", hint="Set case_id in config/agent_config.json or CASE_ID env")
            raise SystemExit(1)
        print(format_pending_approvals_text(case_id))
        raise SystemExit(0)

    if args.approve:
        if not case_id:
            log_warning("case_id_missing", hint="Set case_id in config/agent_config.json or CASE_ID env")
            raise SystemExit(1)
        ok = approve_fingerprint(case_id, args.approve, approved_by=args.approved_by)
        if ok:
            print(f"Approved fingerprint {args.approve} for case {case_id}")
            raise SystemExit(0)
        print(f"Fingerprint not found in pending list: {args.approve}")
        raise SystemExit(1)

    if not case_id:
        log_warning("case_id_missing", hint="Set case_id in config/agent_config.json or CASE_ID env")
        raise SystemExit(1)

    if args.reset_memory:
        memory = reset_agent_memory(case_id)
    else:
        memory = load_agent_memory(case_id)
        memory["case_id"] = case_id

    mcp_registry = MCPRegistry.from_config(config)
    portal = CasePortalBridge(mcp_registry.platform_bridge())
    mcp_tool_names = mcp_registry.list_tools()

    execution_cfg = config.get("execution", {})
    executor = MCPExecutor(
        mcp_registry,
        max_output_chars=execution_cfg.get("max_output_chars", 8000),
    )
    policy = MCPPolicyChecker()
    reply_guardrail = ReplyGuardrail(config, policy_checker=policy)
    analyzer = CommentAnalyzer(
        config,
        mcp_tool_names=mcp_tool_names,
        policy_checker=policy,
        allow_host_exec=mcp_registry.has_exec_provider(),
    )
    composer = ReplyComposer(config)
    collaboration = CollaborationReasoner(config)

    deps = WorkflowDeps(
        portal=portal,
        executor=executor,
        policy=policy,
        reply_guardrail=reply_guardrail,
        analyzer=analyzer,
        interpreter=ResultInterpreter(config),
        collaboration=collaboration,
        convergence=CaseConvergenceAssessor(config),
        composer=composer,
        config=config,
        audit=None,
    )
    app = build_workflow(deps)

    require_llm(config.get("llm", {}))
    resolver = ParticipantResolver(config)
    trigger_cfg = TriggerConfig(config)
    log_info(
        "agent_started",
        case_id=case_id,
        dry_run=args.dry_run,
        mcp_tools=len(mcp_tool_names),
        trigger_mode=trigger_cfg.mode,
    )

    try:
        while memory.get("status") != "RESOLVED":
            process_poll_cycle(
                memory,
                config,
                portal,
                app,
                analyzer,
                resolver,
                trigger_cfg,
                deps,
                dry_run=args.dry_run,
            )
    except KeyboardInterrupt:
        log_info("agent_stopped", reason="keyboard_interrupt")
        # Save memory so handled comments aren't reprocessed on next start.
        save_agent_memory(memory)
    finally:
        mcp_registry.close()

    log_info("agent_finished")


if __name__ == "__main__":
    main()
