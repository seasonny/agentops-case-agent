"""DecisionEngine — facade over policy checks and human approval gates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.approval import (
    filter_unapproved_actions,
    format_approval_required_reply,
    register_pending_approvals,
)
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.decision.models import DecisionContext, DecisionResult


class DecisionEngine:
    """Central governance entry — delegates to policy and approval modules."""

    def __init__(
        self,
        policy: MCPPolicyChecker,
        config: Dict[str, Any],
    ):
        self.policy = policy
        self.config = config

    def evaluate(self, context: DecisionContext) -> DecisionResult:
        """Evaluate whether proposed actions may proceed (policy phase)."""
        return self._evaluate_policy(context)

    def evaluate_policy(
        self,
        *,
        action_type: str,
        actions: Sequence[MCPAction],
        latest_msg: str,
        blocked_commands: Optional[List[str]] = None,
        comment_id: Optional[int] = None,
        dry_run: bool = False,
    ) -> DecisionResult:
        context = DecisionContext(
            action_type=action_type,
            actions=list(actions),
            latest_msg=latest_msg,
            blocked_commands=list(blocked_commands or []),
            comment_id=comment_id,
            dry_run=dry_run,
        )
        return self._evaluate_policy(context)

    def evaluate_approval(
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
        )
        tools = [action.tool for action in blocked]
        log_info(
            "approval_required",
            comment_id=comment_id,
            pending=[item.get("fingerprint") for item in pending],
        )
        return DecisionResult(
            allowed=False,
            reason=format_approval_required_reply(pending),
            policy_ref="approval",
            requires_approval=True,
            risk_hint=", ".join(tools),
            approval_pending=pending,
        )

    def _evaluate_policy(self, context: DecisionContext) -> DecisionResult:
        action_type = context.action_type
        actions = list(context.actions)
        latest_msg = context.latest_msg
        blocked_commands = list(context.blocked_commands)
        policy_ref = f"policy:{self.policy.profile}"

        if self.policy.dangerous_handling == "reject_all":
            is_dangerous, matched = self.policy.is_dangerous_command(latest_msg)
            if is_dangerous:
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
        elif blocked_commands:
            log_info(
                "dangerous_command_partial_skip",
                blocked=blocked_commands,
                comment_id=context.comment_id,
            )

        if action_type != "call_mcp" or not actions:
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
            )

        passed, reason = self.policy.check_all(actions)
        if not passed:
            log_warning(
                "policy_blocked",
                tools=[action.tool for action in actions],
                reason=reason,
            )
            return DecisionResult(
                allowed=False,
                reason=reason,
                policy_ref=policy_ref,
                risk_hint=", ".join(action.tool for action in actions),
                blocked_commands=blocked_commands,
            )

        log_info("policy_passed", tools=[action.tool for action in actions])
        partial_reason = "Passed"
        if blocked_commands:
            skipped = ", ".join(blocked_commands)
            partial_reason = f"Passed (skipped dangerous: {skipped})"
        return DecisionResult(
            allowed=True,
            reason=partial_reason,
            policy_ref=policy_ref,
            blocked_commands=blocked_commands,
        )
