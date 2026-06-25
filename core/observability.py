"""Health check and observability for Enterprise deployments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from bridges.mcp_registry import MCPRegistry
from core.config import iter_mcp_provider_specs
from core.enterprise import audit_trail_enabled, tenant_id
from core.llm_client import is_llm_available
from core.outage import is_outage_mode
from core.policy_compiler import load_compiled_policy


def _check_llm(config: Dict[str, Any]) -> Dict[str, Any]:
    llm = config.get("llm", {})
    ok = is_llm_available(llm)
    return {
        "ok": ok,
        "provider": llm.get("provider"),
        "model": llm.get("model"),
    }


def _check_mcp(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    specs = iter_mcp_provider_specs(config)
    if not specs:
        return [{"name": "mcp", "ok": False, "detail": "no providers"}]

    registry = MCPRegistry.from_config(config)
    results: List[Dict[str, Any]] = []
    try:
        for name, provider in registry.providers.items():
            bridge = provider.bridge
            if not bridge.proc:
                results.append({"name": name, "ok": False, "detail": "process not started"})
                continue
            tools = bridge.list_tools()
            results.append({
                "name": name,
                "ok": bool(tools),
                "tool_count": len(tools),
            })
    finally:
        registry.close()
    return results


def build_health_report(config: Dict[str, Any], *, case_id: str = "") -> Dict[str, Any]:
    llm = _check_llm(config)
    mcp = _check_mcp(config)

    policy_ok = True
    policy_profile = ""
    try:
        compiled = load_compiled_policy()
        policy_profile = compiled.profile
        policy_mode = compiled.mode
    except Exception as exc:
        policy_ok = False
        policy_profile = str(exc)
        policy_mode = ""

    mcp_ok = all(item.get("ok") for item in mcp) if mcp else False
    overall = llm["ok"] and mcp_ok and policy_ok

    return {
        "status": "healthy" if overall else "degraded",
        "ts": datetime.now(timezone.utc).isoformat(),
        "case_id": case_id or config.get("case_id", ""),
        "tenant_id": tenant_id(config) or None,
        "outage_mode": is_outage_mode(config),
        "audit_trail": audit_trail_enabled(config),
        "llm": llm,
        "mcp_providers": mcp,
        "policy": {
            "ok": policy_ok,
            "profile": policy_profile if policy_ok else None,
            "mode": policy_mode if policy_ok else None,
            "error": None if policy_ok else policy_profile,
        },
    }


def format_health_text(report: Dict[str, Any]) -> str:
    lines = [
        f"Case Agent Health — {report.get('status', 'unknown').upper()}",
        f"時間：{report.get('ts', '')[:19]}",
    ]
    if report.get("tenant_id"):
        lines.append(f"Tenant：{report['tenant_id']}")
    if report.get("case_id"):
        lines.append(f"Case：{report['case_id']}")
    lines.append(f"Outage 模式：{'是' if report.get('outage_mode') else '否'}")
    lines.append(f"Audit trail：{'開' if report.get('audit_trail') else '關'}")

    llm = report.get("llm", {})
    lines.append(f"LLM：{'OK' if llm.get('ok') else 'FAIL'} ({llm.get('provider')}/{llm.get('model')})")

    lines.append("MCP providers：")
    for item in report.get("mcp_providers", []):
        mark = "OK" if item.get("ok") else "FAIL"
        detail = item.get("tool_count", item.get("detail", ""))
        lines.append(f"  [{mark}] {item.get('name')}: {detail}")

    policy = report.get("policy", {})
    if policy.get("ok"):
        lines.append(f"Policy：{policy.get('profile')} / {policy.get('mode')}")
    else:
        lines.append(f"Policy：FAIL — {policy.get('error')}")

    return "\n".join(lines)


def print_health_json(config: Dict[str, Any], *, case_id: str = "") -> str:
    report = build_health_report(config, case_id=case_id)
    return json.dumps(report, indent=2, ensure_ascii=False)
