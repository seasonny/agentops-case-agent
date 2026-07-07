"""Connector protocol — product-agnostic operational system boundary."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    """Read external events and send agent responses.

    Poll interval and session limits stay in the Workflow Engine runtime;
    connectors only surface what changed in the operational system.
    """

    def poll_events(
        self,
        case_id: str,
        *,
        start_date: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return normalized comment/event dicts, or None when unavailable."""
        ...

    def fetch_context(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Return case/ticket metadata for grounding, if available."""
        ...

    def send_response(self, case_id: str, text: str) -> Dict[str, Any]:
        """Post an agent reply. Returns ``{success: bool, ...}``."""
        ...

    def list_attachments(self, case_id: str) -> List[Dict[str, Any]]:
        """List attachment metadata for verification flows."""
        ...
