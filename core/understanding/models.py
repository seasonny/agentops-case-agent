from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.mcp_action import MCPAction

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
    """Structured output of Understanding — suggests actions, does not authorize them."""

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
