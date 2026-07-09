"""DecisionEngine — unified governance entry for policy and approval gates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.approval import (
    actions_covered_by_resume_grant,
    filter_unapproved_actions,
    format_approval_required_reply,
    register_pending_approvals,
)
from core.dangerous_command_split import DangerousSplitResult, split_comment_requests
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.decision.models import DecisionContext, DecisionResult


class DecisionEngine:
    """Central governance entry — policy, dangerous filtering, and approval."""

    def __init__(
        self,
        policy: MCPPolicyChecker,
        config: Dict[str, Any],
    ):
        self.policy = policy
        self.config = config

    def evaluate(self, context: DecisionContext) -> DecisionResult:
        """Single governance gate: dangerous split, policy, and approval."""
        return self._evaluate(context, include_approval=True)

    def evaluate_policy(
        self,
        *,
        action_type: str,
        actions: Sequence[MCPAction],
        latest_msg: str,
        blocked_commands: Optional[List[str]] = None,
        comment_id: Optional[int] = None,
        case_id: str = "",
        dry_run: bool = False,
    ) -> DecisionResult:
        context = DecisionContext(
            action_type=action_type,
            actions=list(actions),
            latest_msg=latest_msg,
            blocked_commands=list(blocked_commands or []),
            comment_id=comment_id,
            case_id=case_id,
            dry_run=dry_run,
        )
        return self._evaluate(context, include_approval=False)

    def evaluate_approval(
        self,
        *,
        case_id: str,
        actions: Sequence[MCPAction],
        comment_id: Optional[int] = None,
    ) -> DecisionResult:
        return self._evaluate_approval(
            case_id=case_id,
            actions=list(actions),
            comment_id=comment_id,
        )

    def _evaluate(
        self,
        context: DecisionContext,
        *,
        include_approval: bool,
    ) -> DecisionResult:
        policy_ref = f"policy:{self.policy.profile}"
        split = split_comment_requests(
            context.latest_msg,
            self.policy.is_dangerous_command,
            dangerous_handling=self.policy.dangerous_handling,
        )
        blocked_commands = self._merge_blocked_commands(context, split)
        action_type = context.action_type

        if split.reject_entire:
            matched = split.blocked_lines[0] if split.blocked_lines else context.latest_msg
            log_warning(
                "dangerous_command_blocked",
                matched=matched,
                comment_id=context.comment_id,
            )
            return DecisionResult(
                allowed=False,
                reason=(
                    f"安全政策攔截：指令 `{matched}` 屬於危險系統操作，"
                    "禁止執行。請提供其他非破壞性的診斷方式。"
                ),
                policy_ref=policy_ref,
                risk_hint="dangerous_command",
                dangerous_command_blocked=True,
                dangerous_command_matched=matched,
                action_type_override="dangerous_command",
                blocked_commands=blocked_commands,
            )

        filtered_actions, action_block = self._filter_dangerous_actions(context.actions)
        if action_block is not None:
            action_block.blocked_commands = blocked_commands
            return action_block

        if action_type != "call_mcp" or not filtered_actions:
            if blocked_commands and action_type == "dangerous_command":
                matched = blocked_commands[0]
                return DecisionResult(
                    allowed=False,
                    reason=(
                        f"安全政策攔截：指令 `{matched}` 屬於危險系統操作，"
                        "禁止執行。請提供其他非破壞性的診斷方式。"
                    ),
                    policy_ref=policy_ref,
                    risk_hint="dangerous_command",
                    dangerous_command_blocked=True,
                    dangerous_command_matched=matched,
                    action_type_override="dangerous_command",
                    blocked_commands=blocked_commands,
                )
            log_info("policy_skip", reason="no_mcp_execution", action_type=action_type)
            return DecisionResult(
                allowed=True,
                reason="No MCP actions to run.",
                policy_ref=policy_ref,
                blocked_commands=blocked_commands,
                allowed_actions=filtered_actions,
            )

        passed, reason = self.policy.check_all(filtered_actions)
        if not passed:
            log_warning(
                "policy_blocked",
                tools=[action.tool for action in filtered_actions],
                reason=reason,
            )
            return DecisionResult(
                allowed=False,
                reason=reason,
                policy_ref=policy_ref,
                risk_hint=", ".join(action.tool for action in filtered_actions),
                blocked_commands=blocked_commands,
                allowed_actions=filtered_actions,
            )

        partial_reason = "Passed"
        if blocked_commands:
            skipped = ", ".join(blocked_commands)
            partial_reason = f"Passed (skipped dangerous: {skipped})"

        if include_approval and context.case_id:
            if (
                context.resume_pending_id
                and actions_covered_by_resume_grant(
                    context.case_id,
                    context.resume_pending_id,
                    filtered_actions,
                )
            ):
                log_info(
                    "approval_resume_grant",
                    pending_id=context.resume_pending_id,
                    tools=[action.tool for action in filtered_actions],
                )
            else:
                approval = self._evaluate_approval(
                    case_id=context.case_id,
                    actions=filtered_actions,
                    comment_id=context.comment_id,
                )
                if not approval.allowed:
                    approval.blocked_commands = blocked_commands
                    approval.allowed_actions = filtered_actions
                    return approval

        log_info("policy_passed", tools=[action.tool for action in filtered_actions])
        return DecisionResult(
            allowed=True,
            reason=partial_reason,
            policy_ref=policy_ref,
            blocked_commands=blocked_commands,
            allowed_actions=filtered_actions,
        )

    def _merge_blocked_commands(
        self,
        context: DecisionContext,
        split: DangerousSplitResult,
    ) -> List[str]:
        merged: List[str] = list(context.blocked_commands)
        if split.blocked_lines:
            if split.reject_entire:
                log_info(
                    "dangerous_command_precheck",
                    blocked=split.blocked_lines,
                    handling=self.policy.dangerous_handling,
                    comment_id=context.comment_id,
                )
            else:
                log_info(
                    "dangerous_command_skipped",
                    blocked=split.blocked_lines,
                    safe=split.safe_lines,
                    handling=self.policy.dangerous_handling,
                    comment_id=context.comment_id,
                )
        for line in split.blocked_lines:
            if line not in merged:
                merged.append(line)
        return merged

    def _filter_dangerous_actions(
        self,
        actions: Sequence[MCPAction],
    ) -> tuple[List[MCPAction], Optional[DecisionResult]]:
        kept: List[MCPAction] = []
        for action in actions:
            probe_parts = [action.tool]
            argv = action.arguments.get("argv") or action.arguments.get("command")
            if isinstance(argv, list):
                probe_parts.extend(str(part) for part in argv)
            probe = " ".join(probe_parts)
            if self.policy.is_dangerous_command(probe)[0]:
                continue
            kept.append(action)

        if len(kept) == len(actions):
            return kept, None

        if actions and not kept:
            matched = actions[0].label or actions[0].tool
            return [], DecisionResult(
                allowed=False,
                reason=(
                    f"安全政策攔截：所請求的 MCP 操作 `{matched}` 涉及危險指令，"
                    "禁止執行。請提供其他非破壞性的診斷方式。"
                ),
                policy_ref=f"policy:{self.policy.profile}",
                risk_hint="dangerous_command",
                dangerous_command_blocked=True,
                dangerous_command_matched=matched,
                action_type_override="dangerous_command",
            )

        return kept, None

    def _evaluate_approval(
        self,
        *,
        case_id: str,
        actions: Sequence[MCPAction],
        comment_id: Optional[int] = None,
    ) -> DecisionResult:
        blocked = filter_unapproved_actions(case_id, actions, self.config)
        if not blocked:
            return DecisionResult(
                allowed=True,
                reason="Approval not required or already granted.",
                policy_ref="approval",
            )

        pending = register_pending_approvals(
            case_id,
            blocked,
            comment_id=comment_id,
            config=self.config,
        )
        tools = [action.tool for action in blocked]
        log_info(
            "approval_required",
            comment_id=comment_id,
            pending=[item.get("fingerprint") for item in pending],
        )
        return DecisionResult(
            allowed=False,
            reason=format_approval_required_reply(pending, config=self.config),
            policy_ref="approval",
            requires_approval=True,
            risk_hint=", ".join(tools),
            approval_pending=pending,
        )
