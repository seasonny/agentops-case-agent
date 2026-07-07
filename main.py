#!/usr/bin/env python3
"""AgentOps Case Agent — CLI entry point."""

import argparse
import warnings

warnings.filterwarnings("ignore")

from bridges.case_portal import CasePortalBridge
from bridges.mcp_registry import MCPRegistry
from core.agent_settings import init_agent_settings
from core.approval import approve_fingerprint, format_pending_approvals_text
from core.audit_trail import format_audit_report_text
from core.case_convergence import CaseConvergenceAssessor
from core.collaboration_reasoner import CollaborationReasoner
from core.decision import DecisionEngine
from core.understanding import UnderstandingService
from core.config import load_config
from core.llm_client import require_llm
from core.logging import log_info, log_warning
from core.mcp_action import MCPExecutor
from core.mcp_policy import MCPPolicyChecker
from core.memory import load_agent_memory, reset_agent_memory, save_agent_memory
from core.observability import build_health_report, format_health_text
from core.participants import ParticipantResolver
from core.policy_compiler import load_compiled_policy, policy_to_dict
from core.poc_metrics import format_report_text, summarize_metrics
from core.reply_composer import ReplyComposer
from core.reply_guardrail import ReplyGuardrail
from core.result_interpreter import ResultInterpreter
from core.setup_check import run_setup_check
from core.trigger import TriggerConfig
from workflow.graph import WorkflowDeps, build_workflow
from workflow.runner import process_poll_cycle


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
    decision_engine = DecisionEngine(policy, config)
    reply_guardrail = ReplyGuardrail(config, policy_checker=policy)
    understanding = UnderstandingService(
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
        decision_engine=decision_engine,
        reply_guardrail=reply_guardrail,
        understanding=understanding,
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
                understanding,
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
