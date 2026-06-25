from typing import Any, Dict, Optional

from core.case_context import truncate_for_prompt
from core.config import CONVERGENCE_PROMPT_FILE
from core.llm_client import chat_json
from core.logging import log_info, log_warning

VALID_CASE_STATUS = frozenset({"POLLING", "RESOLVED"})


def _load_template() -> str:
    if CONVERGENCE_PROMPT_FILE.exists():
        return CONVERGENCE_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Assess if case is resolved. History: {case_history} "
        "Findings: {interpretation_findings}"
    )


def _render_prompt(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


class CaseConvergenceAssessor:
    def __init__(self, config: Dict[str, Any]):
        self.llm_config = config.get("llm", {})

    def assess(
        self,
        *,
        case_history: str,
        request_summary: str,
        interpretation_findings: str,
        next_steps: str,
    ) -> Dict[str, Any]:
        fallback = {
            "case_status": "POLLING",
            "converged": False,
            "solution_summary": "",
            "reason": "insufficient signal",
            "source": "fallback",
        }

        template = _load_template()
        prompt = _render_prompt(
            template,
            case_history=truncate_for_prompt(case_history),
            request_summary=request_summary or "(no summary)",
            interpretation_findings=truncate_for_prompt(interpretation_findings or "(none)"),
            next_steps=next_steps or "(none)",
        )
        payload = chat_json(
            self.llm_config,
            system_prompt=(
                "You assess whether a Red Hat support case has converged on a solution. "
                "Respond with JSON only."
            ),
            user_prompt=prompt,
        )
        if not payload:
            log_warning("convergence_fallback")
            return fallback

        case_status = str(payload.get("case_status", "POLLING")).upper()
        if case_status not in VALID_CASE_STATUS:
            case_status = "POLLING"

        converged = bool(payload.get("converged", case_status == "RESOLVED"))
        if converged:
            case_status = "RESOLVED"

        result = {
            "case_status": case_status,
            "converged": converged,
            "solution_summary": str(payload.get("solution_summary", "")),
            "reason": str(payload.get("reason", "")),
            "source": "llm",
        }
        log_info(
            "convergence_assessed",
            case_status=result["case_status"],
            converged=result["converged"],
        )
        return result
