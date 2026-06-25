from typing import Any, Dict, List, Optional

from core.agent_settings import get_reply_prefix
from core.case_context import truncate_for_prompt
from core.collaboration_reply import (
    is_echo_of_support_request,
    is_substantive_collaborative_reply,
)
from core.config import COMPOSE_PROMPT_FILE
from core.constants import AGENT_REPLY_PREFIX
from core.llm_client import chat_text
from core.logging import log_info, log_warning
from core.blocked_command_explain import format_blocked_commands_section, merge_blocked_explanation
from core.mcp_action import MCPAction
from core.mcp_policy import MCPPolicyChecker
from core.turn_context import mcp_results_for_compose

# Generic acknowledgements we should not post.
_LOW_VALUE_REPLY_SNIPPETS = (
    "已收到 Support 的說明",
    "我們會依指示配合後續排查",
    "會依建議安排後續處理",
    "有進展時再回報",
)


def _load_compose_template() -> str:
    if COMPOSE_PROMPT_FILE.exists():
        return COMPOSE_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Write a case reply starting with {agent_reply_prefix}. "
        "Context: {request_summary}. Results: {mcp_results}"
    )


def _format_mcp_block(actions: List[MCPAction], results: List[str]) -> str:
    if not actions:
        return ""
    lines = []
    for action, output in zip(actions, results):
        lines.append(f"[{action.display_label()}]\n{output or '(無輸出)'}")
    return "\n---\n".join(lines)


def _format_actions_list(actions: List[MCPAction]) -> str:
    if not actions:
        return "(none)"
    return ", ".join(action.display_label() for action in actions)


def _format_approval_pending(pending: Optional[List[Dict[str, Any]]]) -> str:
    items = pending or []
    if not items:
        return "(none)"
    lines = []
    for item in items:
        fp = item.get("fingerprint", "?")
        label = item.get("label") or item.get("tool", "?")
        lines.append(f"- [{fp}] {label}")
    return "\n".join(lines)


def _join_facts(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _has_mcp_substance(mcp_actions: List[MCPAction], mcp_results: List[str]) -> bool:
    if not mcp_actions:
        return False
    joined = _format_mcp_block(mcp_actions, mcp_results)
    return bool(joined.strip()) and joined.strip() != "(none)"


def _has_text_substance(*texts: str) -> bool:
    for text in texts:
        cleaned = (text or "").strip()
        if not cleaned or cleaned in ("(none)", "N/A"):
            continue
        if any(snippet in cleaned for snippet in _LOW_VALUE_REPLY_SNIPPETS):
            continue
        return True
    return False


def _fallback_reply(
    *,
    action_type: str,
    mcp_actions: List[MCPAction],
    mcp_results: List[str],
    policy_passed: bool,
    policy_reason: str,
    clarifying_questions: List[str],
    interpretation_findings: str,
    next_steps: List[str],
    request_summary: str,
    blocked_commands: Optional[List[str]] = None,
    policy_checker: Optional[MCPPolicyChecker] = None,
    diag_bundle_uploaded: bool = False,
    diag_bundle_filename: str = "",
    diag_bundle_upload_result: str = "",
    collection_uploaded: bool = False,
    collection_upload_filename: str = "",
    collection_upload_result: str = "",
    attachment_verified: bool = False,
    attachment_verify_detail: str = "",
    approval_pending: Optional[List[Dict[str, Any]]] = None,
    collaboration_draft: str = "",
) -> Optional[str]:
    """Minimal factual reply when LLM compose is unavailable or low-value."""
    prefix = get_reply_prefix()
    blocked = [cmd for cmd in (blocked_commands or []) if str(cmd).strip()]
    checker = policy_checker or MCPPolicyChecker()
    blocked_section = format_blocked_commands_section(blocked, checker)

    if not policy_passed:
        return _join_facts(
            prefix,
            blocked_section,
            "安全政策拒絕執行所請求的 MCP 操作。",
            f"原因: {policy_reason}",
        )

    if action_type == "dangerous_command" and blocked_section:
        return _join_facts(prefix, blocked_section)

    if action_type == "clarify" and clarifying_questions:
        draft = (collaboration_draft or "").strip()
        if draft and not is_echo_of_support_request(draft, request_summary):
            return _join_facts(prefix, blocked_section, draft)
        questions = "\n".join(f"- {q}" for q in clarifying_questions)
        return _join_facts(prefix, blocked_section, questions)

    approval_pending = approval_pending or []
    if action_type == "approval_required" and approval_pending:
        from core.approval import format_approval_required_reply

        return _join_facts(prefix, format_approval_required_reply(approval_pending))

    if action_type == "reply_only":
        draft = (collaboration_draft or "").strip()
        findings = (interpretation_findings or "").strip()
        if (
            draft
            and not is_echo_of_support_request(draft, request_summary)
            and is_substantive_collaborative_reply(draft)
        ):
            return _join_facts(prefix, blocked_section, draft)
        if (
            findings
            and _has_text_substance(findings)
            and not is_echo_of_support_request(findings, request_summary)
            and is_substantive_collaborative_reply(findings)
        ):
            return _join_facts(prefix, blocked_section, findings)
        return None

    mcp_body = _format_mcp_block(mcp_actions, mcp_results)
    if _has_mcp_substance(mcp_actions, mcp_results):
        facts: List[str] = []
        findings = (interpretation_findings or "").strip()
        if findings and _has_text_substance(findings):
            facts.append(findings)
        elif (request_summary or "").strip() not in ("", "(none)", "N/A"):
            facts.append((request_summary or "").strip())
        if diag_bundle_uploaded and diag_bundle_filename:
            facts.append(f"診斷輸出已上傳附件: `{diag_bundle_filename}`")
        elif diag_bundle_filename and diag_bundle_upload_result:
            facts.append(
                f"診斷 bundle `{diag_bundle_filename}` 上傳失敗: {diag_bundle_upload_result}"
            )
        if collection_uploaded and collection_upload_filename:
            upload_fact = f"已上傳附件: `{collection_upload_filename}`"
            if attachment_verified:
                upload_fact += "（Case 附件清單已確認）"
            elif attachment_verify_detail:
                upload_fact += f"（{attachment_verify_detail}）"
            facts.append(upload_fact)
        elif collection_upload_filename and collection_upload_result:
            facts.append(
                f"收集完成，上傳 `{collection_upload_filename}` 失敗: {collection_upload_result}"
            )
        facts.append(mcp_body)
        if next_steps:
            facts.append("後續步驟:\n" + "\n".join(f"- {s}" for s in next_steps))
        return _join_facts(prefix, blocked_section, *facts)

    if _has_text_substance(interpretation_findings):
        parts = [interpretation_findings.strip()]
        if next_steps:
            parts.append("後續步驟:\n" + "\n".join(f"- {s}" for s in next_steps))
        return _join_facts(prefix, blocked_section, *parts)

    if diag_bundle_filename and not diag_bundle_uploaded and diag_bundle_upload_result:
        return _join_facts(
            prefix,
            blocked_section,
            f"已產生 `{diag_bundle_filename}`，上傳失敗: {diag_bundle_upload_result}",
        )

    if collection_upload_filename and not collection_uploaded and collection_upload_result:
        return _join_facts(
            prefix,
            blocked_section,
            f"收集完成，上傳 `{collection_upload_filename}` 失敗: {collection_upload_result}",
        )

    return None


def _compose_system_prompt(action_type: str) -> str:
    base = (
        "You are a small ops assistant (小幫手) writing Red Hat case replies "
        "for the customer's SRE team. Sound collaborative and natural — "
        "like a colleague working with Support, not a template bot. "
        "Never repeat Support's latest comment verbatim. "
        "Write AS the customer team speaking TO Support."
    )
    if action_type in ("reply_only", "clarify"):
        return (
            f"{base} "
            "This turn is collaborative text only — no new MCP output required. "
            "Acknowledge Support's point and state what the customer will do next."
        )
    return (
        f"{base} "
        "Never post empty acknowledgements like 'received your message'. "
        "Include concrete findings, command output, or specific questions when available."
    )


def _ensure_prefix(text: str) -> str:
    prefix = get_reply_prefix()
    stripped = text.strip()
    if stripped.startswith(prefix):
        return stripped
    return f"{prefix}\n{stripped}"


def _is_low_value_reply(text: str, *, request_summary: str = "") -> bool:
    prefix = get_reply_prefix()
    body = text.replace(prefix, "").strip()
    if not body or len(body) < 20:
        return True
    if request_summary and is_echo_of_support_request(body, request_summary):
        return True
    if not is_substantive_collaborative_reply(body):
        if any(snippet in body for snippet in _LOW_VALUE_REPLY_SNIPPETS):
            return True
    return False


def _compose_collaborative_reply(
    *,
    action_type: str,
    collaboration_draft: str,
    interpretation_findings: str,
    request_summary: str,
    clarifying_questions: List[str],
    blocked_commands: Optional[List[str]] = None,
    policy_checker: Optional[MCPPolicyChecker] = None,
) -> Optional[str]:
    """Format collaborate output for reply_only / clarify — no second LLM call."""
    return _fallback_reply(
        action_type=action_type,
        mcp_actions=[],
        mcp_results=[],
        policy_passed=True,
        policy_reason="",
        clarifying_questions=clarifying_questions,
        interpretation_findings=interpretation_findings,
        next_steps=[],
        request_summary=request_summary,
        blocked_commands=blocked_commands,
        policy_checker=policy_checker,
        collaboration_draft=collaboration_draft,
    )


def _render_prompt(template: str, **kwargs: str) -> str:
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


class ReplyComposer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})

    def compose(
        self,
        *,
        case_history: str,
        request_summary: str,
        action_type: str,
        mcp_actions: List[MCPAction],
        mcp_results: List[str],
        policy_passed: bool,
        policy_reason: str,
        dangerous_command_matched: str = "",
        blocked_commands: Optional[List[str]] = None,
        policy_checker: Optional[MCPPolicyChecker] = None,
        diag_bundle_uploaded: bool = False,
        diag_bundle_filename: str = "",
        diag_bundle_upload_result: str = "",
        collection_uploaded: bool = False,
        collection_upload_filename: str = "",
        collection_upload_result: str = "",
        attachment_verified: bool = False,
        attachment_verify_detail: str = "",
        approval_pending: Optional[List[Dict[str, Any]]] = None,
        interpretation_findings: str = "",
        next_steps: Optional[List[str]] = None,
        clarifying_questions: Optional[List[str]] = None,
        collaboration_draft: str = "",
    ) -> Optional[str]:
        questions = clarifying_questions or []
        steps = next_steps or []
        blocked = blocked_commands or []
        checker = policy_checker or MCPPolicyChecker()
        blocked_section = format_blocked_commands_section(blocked, checker)
        effective_results = mcp_results_for_compose(
            action_type=action_type,
            mcp_actions=mcp_actions,
            mcp_results=mcp_results,
        )
        if action_type in ("reply_only", "clarify"):
            collaborative = _compose_collaborative_reply(
                action_type=action_type,
                collaboration_draft=collaboration_draft,
                interpretation_findings=interpretation_findings,
                request_summary=request_summary,
                clarifying_questions=questions,
                blocked_commands=blocked,
                policy_checker=checker,
            )
            if collaborative:
                return collaborative
            log_info(
                "reply_skipped_no_substance",
                action_type=action_type,
                reason="collaborative_turn_no_llm_content",
            )
            return None

        fallback = _fallback_reply(
            action_type=action_type,
            mcp_actions=mcp_actions,
            mcp_results=effective_results,
            policy_passed=policy_passed,
            policy_reason=policy_reason,
            clarifying_questions=questions,
            interpretation_findings=interpretation_findings,
            next_steps=steps,
            request_summary=request_summary,
            blocked_commands=blocked,
            policy_checker=checker,
            diag_bundle_uploaded=diag_bundle_uploaded,
            diag_bundle_filename=diag_bundle_filename,
            diag_bundle_upload_result=diag_bundle_upload_result,
            collection_uploaded=collection_uploaded,
            collection_upload_filename=collection_upload_filename,
            collection_upload_result=collection_upload_result,
            attachment_verified=attachment_verified,
            attachment_verify_detail=attachment_verify_detail,
            approval_pending=approval_pending or [],
            collaboration_draft=collaboration_draft,
        )

        mcp_results_for_prompt = _format_mcp_block(mcp_actions, effective_results) or "(none)"
        if diag_bundle_uploaded and diag_bundle_filename:
            mcp_results_for_prompt = (
                f"(Full output uploaded as attachment `{diag_bundle_filename}`. "
                f"Preview below.)\n"
                + truncate_for_prompt(mcp_results_for_prompt, max_chars=1500)
            )
        elif collection_uploaded and collection_upload_filename:
            mcp_results_for_prompt = (
                f"(Collection uploaded as `{collection_upload_filename}`. Preview below.)\n"
                + truncate_for_prompt(mcp_results_for_prompt, max_chars=1500)
            )

        template = _load_compose_template()
        prompt = _render_prompt(
            template,
            agent_reply_prefix=get_reply_prefix(),
            case_history=truncate_for_prompt(case_history),
            request_summary=request_summary or "(no summary)",
            action_type=action_type,
            mcp_actions=_format_actions_list(mcp_actions),
            policy_passed=str(policy_passed),
            policy_reason=policy_reason or "N/A",
            dangerous_command_matched=dangerous_command_matched or "(none)",
            blocked_commands="\n".join(f"- {cmd}" for cmd in blocked) or "(none)",
            blocked_commands_explanation=blocked_section or "(none)",
            diag_bundle_uploaded=str(diag_bundle_uploaded),
            diag_bundle_filename=diag_bundle_filename or "(none)",
            diag_bundle_upload_result=diag_bundle_upload_result or "(none)",
            collection_uploaded=str(collection_uploaded),
            collection_upload_filename=collection_upload_filename or "(none)",
            collection_upload_result=collection_upload_result or "(none)",
            attachment_verified=str(attachment_verified),
            attachment_verify_detail=attachment_verify_detail or "(none)",
            approval_pending=_format_approval_pending(approval_pending),
            interpretation_findings=truncate_for_prompt(
                interpretation_findings or "(none)", max_chars=4000
            ),
            next_steps="\n".join(f"- {s}" for s in steps) or "(none)",
            mcp_results=truncate_for_prompt(mcp_results_for_prompt, max_chars=8000),
            clarifying_questions="\n".join(f"- {q}" for q in questions) or "(none)",
            collaboration_draft=truncate_for_prompt(
                collaboration_draft or "(none)", max_chars=2000
            ),
        )

        composed = chat_text(
            self.llm_config,
            system_prompt=_compose_system_prompt(action_type),
            user_prompt=prompt,
        )
        if composed:
            reply = _ensure_prefix(composed)
            if blocked_section:
                reply = merge_blocked_explanation(reply, blocked_section)
            if not _is_low_value_reply(reply, request_summary=request_summary):
                return reply
            log_warning("reply_compose_low_value", action_type=action_type)

        if fallback:
            log_warning("reply_compose_fallback", action_type=action_type)
            return fallback

        log_info("reply_skipped_no_substance", action_type=action_type)
        return None
