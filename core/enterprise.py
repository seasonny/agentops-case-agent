"""Enterprise configuration helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _section(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    raw = config.get(name, {})
    return raw if isinstance(raw, dict) else {}


def enterprise_section(config: Dict[str, Any]) -> Dict[str, Any]:
    return _section(config, "enterprise")


def outage_section(config: Dict[str, Any]) -> Dict[str, Any]:
    return _section(config, "outage")


def approval_section(config: Dict[str, Any]) -> Dict[str, Any]:
    return _section(config, "approval")


def case_context_section(config: Dict[str, Any]) -> Dict[str, Any]:
    return _section(config, "case_context")


def secrets_section(config: Dict[str, Any]) -> Dict[str, Any]:
    return _section(config, "secrets")


def tenant_section(config: Dict[str, Any]) -> Dict[str, Any]:
    return _section(config, "tenant")


def audit_trail_enabled(config: Dict[str, Any]) -> bool:
    ent = enterprise_section(config)
    if "audit_trail" in ent:
        return bool(ent.get("audit_trail"))
    return bool(ent.get("audit_trail_enabled", True))


def effective_poll_interval_seconds(config: Dict[str, Any]) -> int:
    outage = outage_section(config)
    if outage.get("enabled"):
        return max(1, int(outage.get("interval_seconds", 5) or 5))
    polling = _section(config, "polling")
    return max(1, int(polling.get("interval_seconds", 10) or 10))


def outage_notify_events(config: Dict[str, Any]) -> List[str]:
    outage = outage_section(config)
    events = outage.get("notify_on", [])
    if isinstance(events, list) and events:
        return [str(e) for e in events]
    return ["reply_posted", "policy_blocked", "approval_required", "clarify"]


def outage_webhook_url(config: Dict[str, Any]) -> str:
    outage = outage_section(config)
    env_name = str(outage.get("notify_webhook_url_env", "CASE_AGENT_WEBHOOK_URL")).strip()
    if env_name:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return str(outage.get("notify_webhook_url", "") or "").strip()


def approval_enabled(config: Dict[str, Any]) -> bool:
    return bool(approval_section(config).get("enabled"))


def approval_required_tools(config: Dict[str, Any]) -> List[str]:
    tools = approval_section(config).get("required_tools", [])
    if isinstance(tools, list) and tools:
        return [str(t).strip() for t in tools if str(t).strip()]
    return [
        "oc_adm_must_gather",
        "pods_exec",
        "upload_attachment_rh_portal",
    ]


def tenant_id(config: Dict[str, Any]) -> str:
    tenant = tenant_section(config)
    value = str(tenant.get("id", "") or "").strip()
    if value:
        return value
    return os.environ.get("CASE_AGENT_TENANT_ID", "").strip()


def tenant_label(config: Dict[str, Any]) -> str:
    return str(tenant_section(config).get("label", "") or "").strip()


def diagnostics_tracking_enabled(config: Dict[str, Any]) -> bool:
    ctx = case_context_section(config)
    return bool(ctx.get("track_diagnostics", True))


def diagnostics_history_limit(config: Dict[str, Any]) -> int:
    ctx = case_context_section(config)
    return max(1, int(ctx.get("max_items", 50) or 50))
