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
    resume_pending_id: Optional[str] = None


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
    allowed_actions: List[MCPAction] = field(default_factory=list)

    def to_workflow_state(self) -> Dict[str, Any]:
        """Map to workflow state after the unified decision node."""
        state: Dict[str, Any] = {
            "policy_passed": self.allowed,
            "policy_reason": self.reason,
            "dangerous_command_blocked": self.dangerous_command_blocked,
            "dangerous_command_matched": self.dangerous_command_matched,
            "blocked_commands": list(self.blocked_commands),
        }
        if self.action_type_override:
            state["action_type"] = self.action_type_override
        if self.requires_approval:
            state.update(
                {
                    "approval_required": True,
                    "approval_pending": list(self.approval_pending),
                    "action_type": "approval_required",
                    "policy_passed": False,
                    "execution_results": [],
                    "status": "POLLING",
                }
            )
        if self.allowed_actions:
            serialized = [
                {
                    "tool": action.tool,
                    "arguments": dict(action.arguments),
                    "label": action.label,
                }
                for action in self.allowed_actions
            ]
            state["mcp_actions"] = serialized
            if not state.get("action_type") or state.get("action_type") == "call_mcp":
                state.setdefault("action_type", "call_mcp")
        return state

    def to_policy_state(self) -> Dict[str, Any]:
        """Backward-compatible alias for workflow/tests."""
        return self.to_workflow_state()

    def to_approval_state(self) -> Dict[str, Any]:
        """Backward-compatible mapping when approval blocks execution."""
        return {
            "execution_results": [],
            "approval_required": True,
            "approval_pending": list(self.approval_pending),
            "action_type": "approval_required",
            "status": "POLLING",
            "policy_passed": False,
            "policy_reason": self.reason,
        }
