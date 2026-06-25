from typing import Any, Dict, List, Optional

from bridges.mcp_bridge import MCPBridge
from core.agent_settings import is_comment_public
from core.case_api_models import (
    parse_attachments_payload,
    parse_case_comments_payload,
    parse_case_detail_payload,
)
from core.comments import parse_rh_portal_comments
from core.logging import log_info, log_warning


def _content_to_text(content: Any) -> str:
    if isinstance(content, list):
        return "; ".join(
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _looks_like_successful_add_comment_tool_error(result: Dict[str, Any]) -> bool:
    """MCP sometimes returns isError=true even when Portal accepted the comment (HTTP 200)."""
    if not isinstance(result, dict) or not result.get("isError"):
        return False
    error_text = _content_to_text(result.get("content"))
    if "failed to add comment" not in error_text:
        return False
    if "status code: 200" not in error_text:
        return False
    return '"commentBody"' in error_text and '"id"' in error_text and '"caseNumber"' in error_text


class CasePortalBridge:
    def __init__(self, mcp_bridge: MCPBridge):
        self.mcp = mcp_bridge

    def _query_case_comments_once(
        self,
        case_id: str,
        *,
        start_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"case-number": case_id}
        if start_date:
            params["start-date"] = start_date
        return self.mcp.call_tool("read_case_comments_rh_portal", params)

    def _parse_comments_result(
        self,
        result: Dict[str, Any],
        *,
        case_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        api_comments = parse_case_comments_payload(result, case_number=case_id)
        if api_comments is not None:
            return api_comments

        if isinstance(result, dict) and "content" in result:
            content_value = result["content"]
            if isinstance(content_value, (str, list)):
                api_comments = parse_case_comments_payload(
                    content_value, case_number=case_id
                )
                if api_comments is not None:
                    return api_comments
                return parse_rh_portal_comments(content_value)

        comments = (
            result.get("comments", result)
            if isinstance(result, list)
            else result.get("comments", [])
        )
        if isinstance(comments, list):
            api_comments = parse_case_comments_payload(comments, case_number=case_id)
            if api_comments is not None:
                return api_comments
            if comments and isinstance(comments[0], dict) and "content" in comments[0]:
                return comments
        return []

    def query_case_comments(
        self,
        case_id: str,
        *,
        start_date: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        result = self._query_case_comments_once(case_id, start_date=start_date)
        retried_after_stale_add = False
        if (
            isinstance(result, dict)
            and result.get("isError")
            and "failed to add comment" in _content_to_text(result.get("content"))
        ):
            log_warning("case_comments_stale_add_comment_error", case_id=case_id)
            result = self._query_case_comments_once(case_id, start_date=start_date)
            retried_after_stale_add = True

        if "error" in result:
            log_warning("case_comments_read_failed", error=result["error"])
            return None

        if isinstance(result, dict) and result.get("isError"):
            error_text = _content_to_text(result.get("content"))
            if retried_after_stale_add:
                log_warning("case_comments_tool_error_after_retry", error=error_text)
            else:
                log_warning("case_comments_tool_error", error=error_text)
            return None

        return self._parse_comments_result(result, case_id=case_id)

    def query_case_detail(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Read case metadata (Hydra getCase). Returns None if MCP tool unavailable."""
        result = self.mcp.call_tool("read_case_rh_portal", {"case-number": case_id})
        if not isinstance(result, dict) or result.get("isError") or "error" in result:
            log_warning("case_detail_read_failed", case_id=case_id)
            return None
        case = parse_case_detail_payload(result)
        if case:
            log_info("case_detail_loaded", case_id=case_id, status=case.get("status"))
        return case

    def list_attachments(self, case_id: str) -> List[Dict[str, Any]]:
        """List case attachment metadata. Returns [] if MCP tool unavailable."""
        result = self.mcp.call_tool(
            "list_case_attachments_rh_portal",
            {"case-number": case_id},
        )
        if not isinstance(result, dict) or result.get("isError") or "error" in result:
            log_warning("case_attachments_list_failed", case_id=case_id)
            return []
        attachments = parse_attachments_payload(result) or []
        log_info("case_attachments_listed", case_id=case_id, count=len(attachments))
        return attachments

    def add_comment(self, case_id: str, text: str) -> Dict[str, Any]:
        result = self.mcp.call_tool(
            "add_case_comment_rh_portal",
            {
                "case-number": case_id,
                "text": text,
                "public": is_comment_public(),
            },
        )

        if "error" in result:
            log_warning("case_comment_add_failed", case_id=case_id, error=result["error"])
            return {"success": False, "result": result}

        if isinstance(result, dict) and result.get("isError"):
            error_text = _content_to_text(result.get("content"))
            if _looks_like_successful_add_comment_tool_error(result):
                log_warning("case_comment_add_soft_success", case_id=case_id, detail=error_text[:240])
                return {"success": True, "result": result}
            log_warning("case_comment_add_tool_error", case_id=case_id, error=error_text[:240])
            return {"success": False, "result": result}

        log_info("case_comment_added", case_id=case_id)
        return {"success": True, "result": result}
