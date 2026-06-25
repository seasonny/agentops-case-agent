from typing import Any, Dict, List, Optional

from core.case_context import truncate_for_prompt
from core.config import INTERPRET_PROMPT_FILE
from core.investigation import filter_follow_up_actions, investigation_settings
from core.llm_client import chat_json
from core.logging import log_warning
from core.mcp_action import build_tools_catalog


def _load_template() -> str:
    if INTERPRET_PROMPT_FILE.exists():
        return INTERPRET_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Interpret MCP results for case. History: {case_history} "
        "Request: {request_summary} Actions: {mcp_actions} Results: {mcp_results}"
    )


def _render_prompt(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


class ResultInterpreter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})

    def interpret(
        self,
        *,
        case_history: str,
        request_summary: str,
        mcp_actions: str,
        mcp_results: str,
        mcp_tool_names: Optional[List[str]] = None,
        investigate_step: int = 0,
    ) -> Dict[str, Any]:
        fallback = {
            "findings": mcp_results[:2000] if mcp_results else "(無執行結果)",
            "next_steps": [],
            "confidence": "low",
            "needs_more_evidence": False,
            "follow_up_mcp_calls": [],
            "source": "fallback",
        }

        inv_settings = investigation_settings(self.config)
        template = _load_template()
        prompt = _render_prompt(
            template,
            case_history=truncate_for_prompt(case_history),
            request_summary=request_summary or "(no summary)",
            mcp_actions=mcp_actions or "(none)",
            mcp_results=truncate_for_prompt(mcp_results or "(none)", max_chars=10000),
            mcp_tools_catalog=build_tools_catalog(mcp_tool_names or []),
            investigate_step=str(investigate_step),
            max_follow_up_steps=str(inv_settings["max_follow_up_steps"]),
        )
        payload = chat_json(
            self.llm_config,
            system_prompt=(
                "You interpret Kubernetes/support diagnostics in a Guardrailed ReAct loop. "
                "Respond with JSON only."
            ),
            user_prompt=prompt,
        )
        if not payload:
            log_warning("interpret_fallback")
            return fallback

        next_steps = payload.get("next_steps", [])
        if not isinstance(next_steps, list):
            next_steps = []

        needs_more = bool(payload.get("needs_more_evidence", False))
        follow_up = filter_follow_up_actions(
            payload.get("follow_up_mcp_calls", []),
            mcp_tool_names=mcp_tool_names or [],
        )
        if needs_more and not follow_up:
            needs_more = False

        return {
            "findings": str(payload.get("findings", fallback["findings"])),
            "next_steps": [str(s) for s in next_steps if str(s).strip()],
            "confidence": str(payload.get("confidence", "medium")),
            "needs_more_evidence": needs_more,
            "follow_up_mcp_calls": follow_up,
            "source": "llm",
        }
