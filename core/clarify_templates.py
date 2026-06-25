"""Scenario-based clarify question templates (not keyword routing)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from core.config import CONFIG_DIR
from core.collection_flow import (
    is_must_gather_request,
    is_sosreport_request,
    is_upload_request,
    extract_explicit_file_paths,
)

CLARIFY_TEMPLATES_FILE = CONFIG_DIR / "clarify_templates.yaml"

_DEFAULT_TEMPLATES: Dict[str, List[str]] = {
    "must_gather_no_mcp": [
        "請提供 must-gather 要在哪個叢集／環境執行？",
        "請提供完整指令（含 namespace／kubeconfig 若需要）與產物路徑。",
        "完成後是否要以 Case 附件上傳？若是，請說明預期檔名。",
    ],
    "sosreport_no_mcp": [
        "請提供 sosreport 要在哪台主機執行？",
        "請提供完整指令與產物路徑／檔名。",
        "是否需上傳至本 Case 附件？",
    ],
    "upload_no_path": [
        "請提供要上傳的檔案完整路徑與檔名。",
        "若檔案在遠端主機，請說明如何取得或是否需先執行收集指令。",
    ],
    "pod_exec_missing_target": [
        "若需從叢集內執行診斷，請提供 namespace 與 pod 名稱。",
        "或請說明是否可改用其他非侵入式查詢方式。",
    ],
    "host_exec_unavailable": [
        "若需在本機或跳板機執行，請提供主機與完整指令。",
        "請說明產物路徑，以及是否需上傳至 Case 附件。",
    ],
    "generic_unmapped": [
        "請提供要在哪台機器／叢集執行、完整指令、產物路徑，以及是否上傳附件。",
    ],
}


def _load_yaml_templates() -> Dict[str, List[str]]:
    path = CLARIFY_TEMPLATES_FILE
    if not path.exists():
        return dict(_DEFAULT_TEMPLATES)
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return dict(_DEFAULT_TEMPLATES)

    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return dict(_DEFAULT_TEMPLATES)

    merged = dict(_DEFAULT_TEMPLATES)
    for key, value in scenarios.items():
        if not isinstance(value, dict):
            continue
        questions = value.get("questions", [])
        if isinstance(questions, list) and questions:
            merged[str(key)] = [str(q).strip() for q in questions if str(q).strip()]
    return merged


def detect_clarify_scenario(
    comment_text: str,
    *,
    action_type: str,
    mcp_tool_names: Sequence[str],
    allow_host_exec: bool,
) -> str:
    text = comment_text or ""
    tools = set(mcp_tool_names or [])

    if is_must_gather_request(text) and "oc_adm_must_gather" not in tools:
        return "must_gather_no_mcp"
    if is_sosreport_request(text):
        return "sosreport_no_mcp"
    if is_upload_request(text) and not extract_explicit_file_paths(text):
        return "upload_no_path"

    shell_only = bool(
        re.search(r"\b(dig|ping|nslookup|curl|traceroute|host)\b", text, re.I)
    )
    if shell_only and "pods_exec" not in tools and not allow_host_exec:
        return "host_exec_unavailable"
    if shell_only and "pods_exec" in tools and "namespace" not in text.lower():
        return "pod_exec_missing_target"

    if action_type in ("clarify", "reply_only"):
        return "generic_unmapped"
    return "generic_unmapped"


def enrich_clarifying_questions(
    comment_text: str,
    *,
    action_type: str,
    existing_questions: Sequence[str],
    mcp_tool_names: Sequence[str],
    allow_host_exec: bool,
) -> List[str]:
    scenario = detect_clarify_scenario(
        comment_text,
        action_type=action_type,
        mcp_tool_names=mcp_tool_names,
        allow_host_exec=allow_host_exec,
    )
    templates = _load_yaml_templates()
    template_questions = list(templates.get(scenario, templates["generic_unmapped"]))

    merged: List[str] = []
    seen: set[str] = set()
    for q in list(existing_questions) + template_questions:
        cleaned = str(q).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        merged.append(cleaned)
    return merged


def should_use_clarify_instead_of_reply_only(
    comment_text: str,
    *,
    mcp_tool_names: Sequence[str],
) -> bool:
    text = comment_text or ""
    if is_must_gather_request(text) and "oc_adm_must_gather" not in mcp_tool_names:
        return True
    if is_sosreport_request(text):
        return True
    if is_upload_request(text) and not extract_explicit_file_paths(text):
        return True
    return False
