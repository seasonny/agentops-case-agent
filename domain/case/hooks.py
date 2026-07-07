"""Case domain workflow hooks — orchestration steps injected into the generic graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from connectors import Connector
from core.audit_trail import AuditTrail
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction, MCPExecutor
from core.mcp_policy import MCPPolicyChecker
from domain.case.collection_flow import process_post_execute_collection
from domain.case.diag_bundle import (
    build_bundle_content,
    build_upload_action,
    should_bundle_outputs,
    write_output_bundle,
)
from domain.case.investigation import serialize_actions, should_continue_investigation


@dataclass
class CaseDomainHooks:
    """Case-specific workflow steps — collection, bundle, investigation loop."""

    config: Dict[str, Any]

    def run_collection_step(
        self,
        *,
        connector: Connector,
        executor: MCPExecutor,
        policy: MCPPolicyChecker,
        case_id: str,
        dry_run: bool,
        action_type: str,
        policy_passed: bool,
        actions: Sequence[MCPAction],
        results: Sequence[str],
    ) -> Dict[str, Any]:
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

        if action_type != "call_mcp" or not actions or not policy_passed:
            return {
                "collection_uploaded": False,
                "collection_upload_filename": "",
                "collection_upload_path": "",
                "collection_upload_result": "",
                "attachment_verified": False,
                "attachment_verify_detail": "",
            }

        outcome = process_post_execute_collection(
            connector=connector,
            executor=executor,
            policy=policy,
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

    def run_bundle_step(
        self,
        *,
        executor: MCPExecutor,
        policy: MCPPolicyChecker,
        case_id: str,
        dry_run: bool,
        actions: Sequence[MCPAction],
        results: Sequence[str],
        blocked_commands: Sequence[str],
    ) -> Dict[str, Any]:
        if not should_bundle_outputs(
            config=self.config,
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
            policy=policy,
        )
        bundle_path = write_output_bundle(self.config, content, case_id=case_id)
        filename = bundle_path.name
        log_info(
            "diag_bundle_written",
            path=str(bundle_path),
            bytes=len(content.encode("utf-8")),
        )

        if dry_run:
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
        passed, reason = policy.check_action(upload_action)
        if not passed:
            log_warning("diag_bundle_upload_blocked", reason=reason)
            return {
                "diag_bundle_uploaded": False,
                "diag_bundle_filename": filename,
                "diag_bundle_path": str(bundle_path),
                "diag_bundle_upload_result": reason,
            }

        upload_result = executor.run_action(upload_action)
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

    def route_after_interpret(self, state: Dict[str, Any]) -> str:
        if should_continue_investigation(state, self.config):
            return "investigate_prepare"
        return "collection"

    def run_investigate_prepare_step(
        self,
        *,
        audit: Optional[AuditTrail],
        comment_id: Optional[int],
        dry_run: bool,
        follow_up_mcp_actions: Sequence[Dict[str, Any]],
        investigate_step: int,
    ) -> Dict[str, Any]:
        follow_up = list(follow_up_mcp_actions)
        next_step = investigate_step + 1
        log_info(
            "investigate_prepare",
            step=next_step,
            tools=[item.get("tool") for item in follow_up if isinstance(item, dict)],
        )
        if audit:
            audit.record(
                "investigate_follow_up",
                comment_id=comment_id,
                dry_run=dry_run,
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

    def serialize_follow_up_actions(self, actions: List[MCPAction]) -> List[Dict[str, Any]]:
        return serialize_actions(actions)
