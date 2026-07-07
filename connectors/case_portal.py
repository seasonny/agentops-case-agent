"""Red Hat Case Portal connector — first Connector implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bridges.case_portal import CasePortalBridge


class CasePortalConnector:
    """Connector facade over :class:`CasePortalBridge` (MCP-backed Portal API)."""

    def __init__(self, bridge: CasePortalBridge):
        self._bridge = bridge

    def poll_events(
        self,
        case_id: str,
        *,
        start_date: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        return self._bridge.query_case_comments(case_id, start_date=start_date)

    def fetch_context(self, case_id: str) -> Optional[Dict[str, Any]]:
        return self._bridge.query_case_detail(case_id)

    def send_response(self, case_id: str, text: str) -> Dict[str, Any]:
        return self._bridge.add_comment(case_id, text)

    def list_attachments(self, case_id: str) -> List[Dict[str, Any]]:
        return self._bridge.list_attachments(case_id)
