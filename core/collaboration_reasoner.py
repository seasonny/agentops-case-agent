"""LLM reasoning for reply_only / clarify turns — collaborative customer voice."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.case_context import truncate_for_prompt
from core.case_context_memory import format_hypothesis_context
from core.collaboration_reply import is_echo_of_support_request, resolve_collaborative_reply
from core.config import COLLABORATE_PROMPT_FILE
from core.llm_client import chat_json
from core.logging import log_warning


def _load_template() -> str:
    if COLLABORATE_PROMPT_FILE.exists():
        return COLLABORATE_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Collaborate on case reply. History: {case_history} "
        "Support said: {request_summary} Action: {action_type}"
    )


def _render_prompt(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _empty_reasoning(*, questions: List[str], source: str) -> Dict[str, Any]:
    return {
        "findings": "",
        "next_steps": list(questions),
        "customer_voice": "",
        "diagnosis_understanding": "",
        "confirmation_questions": [],
        "customer_actions": [],
        "verification_plan": "",
        "convergence_signal": "none",
        "source": source,
    }


class CollaborationReasoner:
    def __init__(self, config: Dict[str, Any]):
        self.llm_config = config.get("llm", {})

    def reason(
        self,
        *,
        case_history: str,
        request_summary: str,
        action_type: str,
        clarifying_questions: Optional[List[str]] = None,
        memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        questions = clarifying_questions or []
        hypothesis_context = (
            format_hypothesis_context(memory) if memory else "(none)"
        )

        template = _load_template()
        prompt = _render_prompt(
            template,
            case_history=truncate_for_prompt(case_history),
            hypothesis_context=hypothesis_context,
            request_summary=request_summary or "(no summary)",
            action_type=action_type,
            clarifying_questions="\n".join(f"- {q}" for q in questions) or "(none)",
        )
        payload = chat_json(
            self.llm_config,
            system_prompt=(
                "You help a customer SRE team collaborate with Red Hat Support. "
                "Respond with JSON only. Never echo Support's message back to Support. "
                "Never produce hollow acknowledgements without concrete diagnosis and actions."
            ),
            user_prompt=prompt,
        )
        if not payload:
            log_warning("collaborate_reason_unavailable", action_type=action_type)
            return _empty_reasoning(questions=questions, source="unavailable")

        customer_actions = _as_str_list(payload.get("customer_actions"))
        confirmation_questions = _as_str_list(payload.get("confirmation_questions"))
        next_steps = _as_str_list(payload.get("next_steps"))
        if not next_steps:
            next_steps = list(dict.fromkeys(customer_actions + confirmation_questions))

        customer_voice = str(payload.get("customer_voice", "")).strip()
        findings = str(payload.get("findings", "")).strip()
        diagnosis_understanding = str(
            payload.get("diagnosis_understanding", "")
        ).strip()
        verification_plan = str(payload.get("verification_plan", "")).strip()
        convergence_signal = str(
            payload.get("convergence_signal", "none")
        ).strip().lower()
        if convergence_signal not in ("none", "partial", "agreed"):
            convergence_signal = "none"

        customer_voice = resolve_collaborative_reply(
            customer_voice=customer_voice,
            findings=findings,
            request_summary=request_summary,
        )
        if not customer_voice and findings and not is_echo_of_support_request(
            findings, request_summary
        ):
            from core.collaboration_reply import is_substantive_collaborative_reply

            if is_substantive_collaborative_reply(findings):
                customer_voice = findings

        return {
            "findings": findings or diagnosis_understanding,
            "next_steps": next_steps,
            "customer_voice": customer_voice,
            "diagnosis_understanding": diagnosis_understanding,
            "confirmation_questions": confirmation_questions,
            "customer_actions": customer_actions,
            "verification_plan": verification_plan,
            "convergence_signal": convergence_signal,
            "source": "llm",
        }
