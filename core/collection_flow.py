"""Collection and upload closed-loop helpers (must-gather, attachments)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.diag_bundle import build_upload_action
from core.logging import log_info, log_warning
from core.mcp_action import MCPAction

_MUST_GATHER_RE = re.compile(
    r"must[\s_-]?gather|oc\s+adm\s+must-gather",
    re.IGNORECASE,
)
_SOSREPORT_RE = re.compile(r"\bsosreport\b", re.IGNORECASE)
_UPLOAD_VERB_RE = re.compile(
    r"\b(upload|attach|attachment|上傳|附件)\b",
    re.IGNORECASE,
)
_MUST_GATHER_ARTIFACT_RE = re.compile(
    r"(/[^\s'\"<>]+must-gather[^\s'\"<>]*\.(?:tar\.gz|tgz|tar))",
    re.IGNORECASE,
)
_EXPLICIT_PATH_RE = re.compile(
    r"(/[\w./-]+\.(?:tar\.gz|tgz|tar|zip|txt|log|yaml|yml|json|xml|gz))",
    re.IGNORECASE,
)


def is_must_gather_request(text: str) -> bool:
    return bool(_MUST_GATHER_RE.search(text or ""))


def is_sosreport_request(text: str) -> bool:
    return bool(_SOSREPORT_RE.search(text or ""))


def is_upload_request(text: str) -> bool:
    return bool(_UPLOAD_VERB_RE.search(text or ""))


def extract_explicit_file_paths(text: str) -> List[str]:
    seen: set[str] = set()
    paths: List[str] = []
    for match in _EXPLICIT_PATH_RE.finditer(text or ""):
        candidate = match.group(1).strip().rstrip(".,;:")
        if candidate not in seen:
            seen.add(candidate)
            paths.append(candidate)
    return paths


def extract_must_gather_artifact_path(result_text: str) -> Optional[str]:
    if not result_text:
        return None
    match = _MUST_GATHER_ARTIFACT_RE.search(result_text)
    if not match:
        return None
    return match.group(1).strip()


def tool_available(tool_name: str, mcp_tool_names: Sequence[str]) -> bool:
    return tool_name in set(mcp_tool_names or [])


def policy_allows_tool(policy, tool_name: str) -> bool:
    passed, _ = policy.check_action(MCPAction(tool=tool_name, arguments={}, label=tool_name))
    return passed


def build_must_gather_action() -> MCPAction:
    return MCPAction(
        tool="oc_adm_must_gather",
        arguments={},
        label="oc adm must-gather",
    )


def build_file_upload_action(case_id: str, file_path: Path) -> MCPAction:
    return MCPAction(
        tool="upload_attachment_rh_portal",
        arguments={
            "case-number": case_id,
            "file": str(file_path),
        },
        label=f"upload {file_path.name}",
    )


def infer_must_gather_analysis(
    comment_text: str,
    *,
    mcp_tool_names: Sequence[str],
    policy,
) -> Optional[Dict[str, Any]]:
    if not is_must_gather_request(comment_text):
        return None
    tool = "oc_adm_must_gather"
    if not tool_available(tool, mcp_tool_names):
        return None
    if not policy_allows_tool(policy, tool):
        return None
    return {
        "summary": "Support requested must-gather collection.",
        "mcp_calls": [build_must_gather_action()],
    }


def infer_explicit_upload_analysis(
    comment_text: str,
    case_id: str,
    *,
    mcp_tool_names: Sequence[str],
    policy,
) -> Optional[Dict[str, Any]]:
    if not is_upload_request(comment_text):
        return None
    tool = "upload_attachment_rh_portal"
    if not tool_available(tool, mcp_tool_names):
        return None
    if not policy_allows_tool(policy, tool):
        return None

    for raw_path in extract_explicit_file_paths(comment_text):
        path = Path(raw_path)
        if not path.is_file():
            continue
        action = build_file_upload_action(case_id, path)
        passed, reason = policy.check_action(action)
        if not passed:
            log_warning("upload_path_policy_blocked", path=raw_path, reason=reason)
            continue
        return {
            "summary": f"Support requested upload of {path.name}.",
            "mcp_calls": [action],
        }
    return None


def find_attachment_by_filename(
    attachments: Sequence[Dict[str, Any]],
    filename: str,
) -> Optional[Dict[str, Any]]:
    target = (filename or "").strip().lower()
    if not target:
        return None
    for item in attachments:
        name = str(item.get("file_name") or "").strip().lower()
        if not name:
            continue
        if name == target or target in name or name in target:
            return item
    return None


def verify_attachment_on_case(
    portal,
    case_id: str,
    filename: str,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    attachments = portal.list_attachments(case_id)
    if not attachments:
        return False, "Case 附件清單為空或無法讀取", None
    matched = find_attachment_by_filename(attachments, filename)
    if matched:
        detail = matched.get("file_name") or filename
        return True, f"已於 Case 附件清單找到 `{detail}`", matched
    names = ", ".join(
        str(a.get("file_name") or "?") for a in attachments[:8]
    )
    return False, f"附件清單中未找到 `{filename}`（現有：{names}）", None


def process_post_execute_collection(
    *,
    portal,
    executor,
    policy,
    case_id: str,
    actions: Sequence[MCPAction],
    execution_results: Sequence[str],
    dry_run: bool,
) -> Dict[str, Any]:
    """After MCP execution: must-gather → upload → verify attachment list."""
    result: Dict[str, Any] = {
        "collection_uploaded": False,
        "collection_upload_filename": "",
        "collection_upload_path": "",
        "collection_upload_result": "",
        "attachment_verified": False,
        "attachment_verify_detail": "",
    }

    if dry_run or not case_id:
        return result

    extra_results: List[str] = list(execution_results)

    for action, output in zip(actions, execution_results):
        if action.tool == "upload_attachment_rh_portal":
            file_arg = ""
            for key in ("file", "path", "file-path", "filepath", "file_path"):
                if key in action.arguments:
                    file_arg = str(action.arguments[key])
                    break
            filename = Path(file_arg).name if file_arg else ""
            if not filename:
                continue
            uploaded_ok = "error" not in str(output).lower()
            result["collection_uploaded"] = uploaded_ok
            result["collection_upload_filename"] = filename
            result["collection_upload_path"] = file_arg
            result["collection_upload_result"] = str(output)
            if uploaded_ok:
                verified, detail, _ = verify_attachment_on_case(
                    portal, case_id, filename
                )
                result["attachment_verified"] = verified
                result["attachment_verify_detail"] = detail
                log_info(
                    "attachment_verify",
                    case_id=case_id,
                    filename=filename,
                    verified=verified,
                )
            else:
                result["attachment_verify_detail"] = "上傳失敗，略過附件驗證"

        elif action.tool == "oc_adm_must_gather":
            artifact = extract_must_gather_artifact_path(str(output))
            if not artifact:
                result["collection_upload_result"] = (
                    "must-gather 已完成，但無法從輸出解析 tarball 路徑"
                )
                continue
            path = Path(artifact)
            if not path.is_file():
                result["collection_upload_path"] = artifact
                result["collection_upload_result"] = (
                    f"must-gather 產物 `{artifact}` 在本機不存在，無法上傳"
                )
                continue
            upload_action = build_upload_action(case_id, path)
            passed, reason = policy.check_action(upload_action)
            if not passed:
                result["collection_upload_result"] = reason
                continue

            upload_output = executor.run_action(upload_action)
            extra_results.append(upload_output)
            uploaded = "error" not in str(upload_output).lower()
            result["collection_uploaded"] = uploaded
            result["collection_upload_filename"] = path.name
            result["collection_upload_path"] = str(path)
            result["collection_upload_result"] = str(upload_output)

            if uploaded:
                verified, detail, _ = verify_attachment_on_case(
                    portal, case_id, path.name
                )
                result["attachment_verified"] = verified
                result["attachment_verify_detail"] = detail
                log_info(
                    "attachment_verify",
                    case_id=case_id,
                    filename=path.name,
                    verified=verified,
                    source="must_gather_follow_up",
                )
            else:
                result["attachment_verify_detail"] = "must-gather 後上傳失敗"

    if len(extra_results) > len(execution_results):
        result["execution_results"] = extra_results

    return result
