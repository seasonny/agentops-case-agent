from typing import Any, Dict, List, Optional

from core.llm_client import chat_json, is_llm_available
from core.mcp_policy import MCPPolicyChecker
from core.understanding.models import VALID_ACTION_TYPES, CommentAnalysis
from core.understanding.service import UnderstandingService

# Backward-compatible re-export for existing imports and test patches.
__all__ = ["CommentAnalysis", "CommentAnalyzer", "VALID_ACTION_TYPES", "chat_json", "is_llm_available"]


class CommentAnalyzer:
    """Backward-compatible facade over :class:`UnderstandingService`."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        mcp_tool_names: Optional[List[str]] = None,
        policy_checker: Optional[MCPPolicyChecker] = None,
        allow_host_exec: bool = False,
    ):
        self._service = UnderstandingService(
            config,
            mcp_tool_names=mcp_tool_names,
            policy_checker=policy_checker,
            allow_host_exec=allow_host_exec,
        )
        self.config = self._service.config
        self.llm_config = self._service.llm_config
        self.mcp_tool_names = self._service.mcp_tool_names
        self.policy = self._service.policy
        self.allow_host_exec = self._service.allow_host_exec

    def analyze(
        self,
        comment_text: str,
        *,
        case_history: str = "",
        comment_author: str = "",
        resolved_role: str = "",
        trigger_reason: str = "",
    ) -> CommentAnalysis:
        return self._service.analyze(
            comment_text,
            case_history=case_history,
            comment_author=comment_author,
            resolved_role=resolved_role,
            trigger_reason=trigger_reason,
            chat_fn=chat_json,
            is_llm_available_fn=is_llm_available,
        )
