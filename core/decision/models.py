from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.mcp_action import MCPAction


@dataclass
class DecisionContext:
    """Inputs for a governance decision — no LLM involvement."""

    action_type: str = "no_action"
    actions: List[MCPAction] = field(default_factory=list)
    latest_msg: str = ""
    blocked_commands: List[str] = field(default_factory=list)
    case_id: str = ""
    comment_id: Optional[int] = None
    dry_run: bool = False


@dataclass
class DecisionResult:
    """Structured governance outcome — auditable and explainable."""

    allowed: bool
    reason: str
    policy_ref: str = ""
    requires_approval: bool = False
    risk_hint: str = ""
    dangerous_command_blocked: bool = False
    dangerous_command_matched: str = ""
    action_type_override: str = ""
    blocked_commands: List[str] = field(default_factory=list)
    approval_pending: List[Dict[str, Any]] = field(default_factory=list)

    def to_policy_state(self) -> Dict[str, Any]:
        """Map to workflow state fields used by the policy node."""
        state: Dict[str, Any] = {
            "policy_passed": self.allowed,
            "policy_reason": self.reason,
            "dangerous_command_blocked": self.dangerous_command_blocked,
            "dangerous_command_matched": self.dangerous_command_matched,
            "blocked_commands": list(self.blocked_commands),
        }
        if self.action_type_override:
            state["action_type"] = self.action_type_override
        return state

    def to_approval_state(self) -> Dict[str, Any]:
        """Map to workflow state fields used when approval blocks execution."""
        return {
            "execution_results": [],
            "approval_required": True,
            "approval_pending": list(self.approval_pending),
            "action_type": "approval_required",
            "status": "POLLING",
        }
