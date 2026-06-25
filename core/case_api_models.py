"""Normalize Red Hat Case Management API (Hydra) payloads for the Case Agent.

Contract: docs/mcp_case_api_integration.md
MCP tools should return JSON matching the shapes parsed here.
"""

import json
from typing import Any, Dict, List, Optional

from core.logging import log_info, log_warning

# Map API createdByType → agent role. Extend after MCP team confirms real enum values.
_SUPPORT_CREATED_BY_TYPES = frozenset({
    "ASSOCIATE",
    "REDHAT",
    "SUPPORT",
    "ENGINEER",
    "RHN_SUPPORT",
})
_CUSTOMER_CREATED_BY_TYPES = frozenset({
    "CUSTOMER",
    "CONTACT",
    "USER",
    "CUSTOMER_CONTACT",
})
_IGNORED_CREATED_BY_TYPES = frozenset({
    "SYSTEM",
    "AUTOMATED",
    "BOT",
})


def map_created_by_type_to_role(created_by_type: str) -> Optional[str]:
    normalized = str(created_by_type or "").strip().upper()
    if not normalized:
        return None
    if normalized in _IGNORED_CREATED_BY_TYPES:
        return "ignored"
    if normalized in _SUPPORT_CREATED_BY_TYPES:
        return "support"
    if normalized in _CUSTOMER_CREATED_BY_TYPES:
        return "customer"
    return None


def _pick_timestamp(raw: Dict[str, Any]) -> str:
    for key in ("publishedDate", "publishedAt", "createdDate", "createdAt", "timestamp"):
        value = raw.get(key)
        if value:
            return str(value).strip()
    return ""


def _pick_body(raw: Dict[str, Any]) -> str:
    for key in ("commentBody", "body", "content"):
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _pick_author(raw: Dict[str, Any]) -> str:
    for key in ("createdBy", "author"):
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "unknown"


def normalize_api_comment(
    raw: Dict[str, Any],
    *,
    positional_id: int,
    case_number: str = "",
) -> Optional[Dict[str, Any]]:
    """Convert one Hydra CaseComment (or MCP-normalized dict) to agent internal shape."""
    if not isinstance(raw, dict):
        return None
    if raw.get("isDraft") is True:
        return None

    body = _pick_body(raw)
    if not body:
        return None

    portal_comment_id = str(
        raw.get("portalCommentId") or raw.get("id") or ""
    ).strip()
    created_by_type = str(
        raw.get("createdByType") or raw.get("api_created_by_type") or ""
    ).strip()
    timestamp = _pick_timestamp(raw)
    api_role = map_created_by_type_to_role(created_by_type)

    return {
        # MCP legacy convention: lower id = newer when sorted for display; positional_id
        # is assigned by the caller based on sort order (newest → id=1).
        "id": positional_id,
        "portal_comment_id": portal_comment_id,
        "case_number": str(raw.get("caseNumber") or case_number or "").strip(),
        "author": _pick_author(raw),
        "timestamp": timestamp,
        "content": body,
        "created_by_type": created_by_type,
        "api_role": api_role,
        "content_type": str(raw.get("contentType") or "").strip(),
        "role": api_role or "unknown",
        "source_format": "api_json",
    }


def normalize_api_comments(
    payload: Any,
    *,
    case_number: str = "",
) -> List[Dict[str, Any]]:
    """Parse MCP/Hydra comments payload into agent comment dicts (oldest → newest)."""
    raw_comments = _extract_comment_list(payload)
    if not raw_comments:
        return []

    sorted_raw = sorted(raw_comments, key=_sort_key_for_raw)

    normalized: List[Dict[str, Any]] = []
    total = len(sorted_raw)
    for index, raw in enumerate(sorted_raw):
        positional_id = total - index  # oldest gets highest id, newest gets 1
        item = normalize_api_comment(
            raw,
            positional_id=positional_id,
            case_number=case_number,
        )
        if item:
            normalized.append(item)

    if normalized:
        log_info(
            "comments_parsed_api_json",
            count=len(normalized),
            case_number=case_number or None,
        )
    return normalized


def normalize_api_case(payload: Any) -> Optional[Dict[str, Any]]:
    """Parse MCP/Hydra case detail into a compact dict for LLM context."""
    case = payload
    if isinstance(payload, dict) and "case" in payload and isinstance(payload["case"], dict):
        case = payload["case"]
    if not isinstance(case, dict):
        return None

    case_number = str(case.get("caseNumber") or case.get("id") or "").strip()
    if not case_number:
        return None

    return {
        "case_number": case_number,
        "status": str(case.get("status") or "").strip(),
        "severity": str(case.get("severity") or "").strip(),
        "summary": str(case.get("summary") or "").strip(),
        "description": str(case.get("description") or "").strip(),
        "product": str(case.get("product") or "").strip(),
        "version": str(case.get("version") or "").strip(),
        "openshift_cluster_id": str(case.get("openshiftClusterID") or "").strip(),
        "openshift_cluster_version": str(
            case.get("openshiftClusterVersion") or ""
        ).strip(),
        "last_modified_date": str(case.get("lastModifiedDate") or "").strip(),
        "resolution_description": str(case.get("resolutionDescription") or "").strip(),
        "source_format": "api_json",
    }


def normalize_api_attachments(payload: Any) -> List[Dict[str, Any]]:
    raw_list = _extract_attachment_list(payload)
    attachments: List[Dict[str, Any]] = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        attachments.append({
            "id": str(raw.get("id") or "").strip(),
            "file_name": str(raw.get("fileName") or "").strip(),
            "size_kb": raw.get("sizeKB"),
            "created_date": str(raw.get("createdDate") or "").strip(),
            "created_by": str(raw.get("createdBy") or "").strip(),
            "is_private": bool(raw.get("isPrivate", False)),
            "download_restricted": bool(raw.get("downloadRestricted", False)),
            "link": str(raw.get("link") or "").strip(),
        })
    return attachments


def _unwrap_mcp_json_text(payload: Any) -> Optional[Any]:
    """Extract JSON object/array from MCP tool result content wrapper."""
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parsed = _try_parse_json_text(item.get("text", ""))
                if parsed is not None:
                    return parsed
    if isinstance(content, str):
        return _try_parse_json_text(content)
    return None


def parse_case_detail_payload(payload: Any) -> Optional[Dict[str, Any]]:
    """Return normalized case if payload is API JSON; None otherwise."""
    if payload is None:
        return None
    case = normalize_api_case(payload)
    if case:
        return case
    unwrapped = _unwrap_mcp_json_text(payload)
    if unwrapped is not None:
        return normalize_api_case(unwrapped)
    return None


def parse_attachments_payload(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Return normalized attachments if payload is API JSON; None otherwise."""
    if payload is None:
        return None
    raw = payload
    if isinstance(payload, dict) and "content" in payload and "attachments" not in payload:
        unwrapped = _unwrap_mcp_json_text(payload)
        if unwrapped is None:
            return None
        raw = unwrapped
    if isinstance(raw, dict) and "attachments" in raw:
        return normalize_api_attachments(raw)
    if isinstance(raw, list):
        return normalize_api_attachments(raw)
    return None


def parse_case_comments_payload(
    payload: Any,
    *,
    case_number: str = "",
) -> Optional[List[Dict[str, Any]]]:
    """Return normalized comments if payload is API JSON; None → use legacy text parser."""
    if payload is None:
        return None
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            if _looks_like_api_comment(payload[0]):
                return normalize_api_comments(payload, case_number=case_number)
        return None
    if not isinstance(payload, dict):
        return None
    if _looks_like_api_comment(payload):
        return normalize_api_comments([payload], case_number=case_number)
    if "comments" in payload and isinstance(payload["comments"], list):
        if payload["comments"] and _looks_like_api_comment(payload["comments"][0]):
            return normalize_api_comments(payload, case_number=case_number)
    # MCP tool result wrapper: content may be JSON string
    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parsed = _try_parse_json_text(item.get("text", ""))
                if parsed is not None:
                    return parse_case_comments_payload(parsed, case_number=case_number)
    if isinstance(content, str):
        parsed = _try_parse_json_text(content)
        if parsed is not None:
            return parse_case_comments_payload(parsed, case_number=case_number)
    return None


def _looks_like_api_comment(raw: Dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    has_body = any(k in raw for k in ("commentBody", "body", "content"))
    has_id = any(k in raw for k in ("id", "portalCommentId"))
    return has_body and has_id


def _extract_comment_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("comments"), list):
            return [item for item in payload["comments"] if isinstance(item, dict)]
    return []


def _extract_attachment_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("attachments"), list):
            return [item for item in payload["attachments"] if isinstance(item, dict)]
    return []


def _sort_key_for_raw(raw: Dict[str, Any]) -> tuple:
    ts = _pick_timestamp(raw)
    portal_id = str(raw.get("portalCommentId") or raw.get("id") or "")
    return (0 if ts else 1, ts, portal_id)


def _try_parse_json_text(text: str) -> Optional[Any]:
    stripped = (text or "").strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        log_warning("case_api_json_parse_failed")
        return None
