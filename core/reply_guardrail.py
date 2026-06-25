"""Outbound reply safety checks before posting to a Support Case."""

import re
from typing import Any, Dict, List, Optional, Tuple

from core.mcp_policy import MCPPolicyChecker
from core.collaboration_reply import is_echo_of_support_request
from core.reply_grounding import check_execution_grounding, reply_claims_diagnostic_output

DEFAULT_SENSITIVE_PATTERNS: List[str] = [
    r"\bsk-[a-zA-Z0-9]{20,}\b",
    r"\bAIza[0-9A-Za-z\-_]{30,}\b",
    r"(?i)(?:password|passwd|secret|api[_-]?key|bearer)\s*[:=]\s*\S{8,}",
    r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
    r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.",
]


class ReplyGuardrail:
    """Deterministic checks on composed replies before they leave the agent."""

    def __init__(
        self,
        config: Dict[str, Any],
        policy_checker: Optional[MCPPolicyChecker] = None,
    ):
        guardrail_cfg = config.get("guardrails", {}).get("reply", {})
        limits = config.get("limits", {})
        self.max_chars = int(
            guardrail_cfg.get("max_chars", limits.get("max_reply_chars", 4000))
        )
        self.block_sensitive = bool(guardrail_cfg.get("block_sensitive_patterns", True))
        self.block_dangerous = bool(guardrail_cfg.get("block_dangerous_commands", True))
        self.block_ungrounded = bool(
            guardrail_cfg.get("block_ungrounded_execution_output", True)
        )
        self.policy = policy_checker or MCPPolicyChecker()
        patterns = guardrail_cfg.get("sensitive_patterns", DEFAULT_SENSITIVE_PATTERNS)
        self._sensitive_res = [re.compile(p) for p in patterns]

    def validate(
        self,
        reply_text: str,
        *,
        allow_dangerous_mention: bool = False,
        action_type: str = "",
        execution_results: Optional[List[str]] = None,
        request_summary: str = "",
        dry_run: bool = False,
        skip_grounding: bool = False,
    ) -> Tuple[bool, str, str]:
        """Return ``(passed, reason, safe_text)``.

        *passed* — ``True`` when the reply may be posted (possibly truncated).
        *safe_text* — text to post; empty when blocked.
        """
        text = (reply_text or "").strip()
        if not text:
            return False, "empty_reply", ""

        if self.block_sensitive:
            for pattern in self._sensitive_res:
                if pattern.search(text):
                    return False, "sensitive_content_detected", ""

        if self.block_dangerous and not allow_dangerous_mention:
            is_dangerous, matched = self.policy.is_dangerous_command(text)
            if is_dangerous:
                return False, f"dangerous_command_in_reply:{matched}", ""

        if self.block_ungrounded and not skip_grounding:
            grounded, ground_reason = check_execution_grounding(
                text,
                action_type=action_type,
                execution_results=execution_results or [],
                dry_run=dry_run,
            )
            if not grounded:
                return False, ground_reason, ""

        if action_type in ("reply_only", "clarify") and reply_claims_diagnostic_output(text):
            return False, "text_only_turn_with_execution_output", ""

        if (
            action_type in ("reply_only", "clarify")
            and request_summary
            and is_echo_of_support_request(text, request_summary)
        ):
            return False, "echo_of_support_message", ""

        if len(text) > self.max_chars:
            truncated = (
                text[: self.max_chars - 40]
                + f"\n\n...(回覆已截斷，原長 {len(text)} 字元)"
            )
            return True, "truncated", truncated

        return True, "ok", text
