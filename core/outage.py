"""Outage mode: faster polling and webhook notifications."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from core.enterprise import (
    effective_poll_interval_seconds,
    outage_notify_events,
    outage_section,
    outage_webhook_url,
)
from core.logging import log_info, log_warning


def is_outage_mode(config: Dict[str, Any]) -> bool:
    return bool(outage_section(config).get("enabled"))


def poll_interval_seconds(config: Dict[str, Any]) -> int:
    return effective_poll_interval_seconds(config)


def should_notify(config: Dict[str, Any], event: str) -> bool:
    if not is_outage_mode(config):
        return False
    if not outage_webhook_url(config):
        return False
    return event in outage_notify_events(config)


def notify_webhook(
    config: Dict[str, Any],
    event: str,
    *,
    case_id: str = "",
    message: str = "",
    fields: Optional[Dict[str, Any]] = None,
) -> bool:
    if not should_notify(config, event):
        return False

    url = outage_webhook_url(config)
    payload = {
        "event": event,
        "case_id": case_id,
        "message": message,
        "fields": fields or {},
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            ok = 200 <= response.status < 300
            log_info("outage_webhook_sent", event=event, case_id=case_id, status=response.status)
            return ok
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log_warning("outage_webhook_failed", event=event, case_id=case_id, error=str(exc))
        return False
