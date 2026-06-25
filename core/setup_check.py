"""Pre-flight checks before running the agent."""

from typing import Any, Dict, List, Tuple

from bridges.mcp_registry import MCPRegistry
from core.config import iter_mcp_provider_specs
from core.llm_client import is_llm_available, require_llm
from core.policy_compiler import (
    PolicyConfigError,
    format_policy_summary,
    load_compiled_policy,
)


def _check_llm(config: Dict[str, Any]) -> Tuple[bool, str]:
    llm = config.get("llm", {})
    provider = llm.get("provider", "openai")
    model = llm.get("model", "")
    if not is_llm_available(llm):
        env_name = llm.get("api_key_env", "OPENAI_API_KEY")
        return False, f"LLM API key not set (export {env_name} or add to .env)"
    try:
        require_llm(llm)
    except Exception as exc:
        return False, f"LLM init failed: {exc}"
    return True, f"LLM OK ({provider}/{model})"


def _check_mcp_providers(config: Dict[str, Any]) -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []
    specs = iter_mcp_provider_specs(config)
    if not specs:
        return [("mcp", False, "No MCP providers configured or discovered")]

    registry = MCPRegistry.from_config(config)
    try:
        for name, provider in registry.providers.items():
            bridge = provider.bridge
            if not bridge.proc:
                results.append((name, False, "process failed to start"))
                continue
            tools = bridge.list_tools()
            if tools:
                results.append((name, True, f"{len(tools)} tools ({tools[0]}, …)"))
            else:
                results.append((name, False, "started but no tools listed"))
    finally:
        registry.close()
    return results


def run_setup_check(config: Dict[str, Any], *, case_id: str = "") -> int:
    """Run all checks. Returns 0 on success, 1 if any failed."""
    case_id = case_id or str(config.get("case_id", "")).strip()
    print("AgentOps Case Agent — setup check\n")

    ok, msg = _check_llm(config)
    print(f"  [{'OK' if ok else 'FAIL'}] {msg}")

    mcp_results = _check_mcp_providers(config)
    mcp_ok = True
    for name, passed, detail in mcp_results:
        print(f"  [{'OK' if passed else 'FAIL'}] MCP {name}: {detail}")
        mcp_ok = mcp_ok and passed

    case_ok = False
    case_msg = "case_id not set (config/agent_config.json or CASE_ID env)"
    if case_id:
        registry = MCPRegistry.from_config(config)
        try:
            portal_bridge = registry.platform_bridge()
            from bridges.case_portal import CasePortalBridge

            portal = CasePortalBridge(portal_bridge)
            comments = portal.query_case_comments(case_id)
            if comments is None:
                case_msg = f"cannot read comments for case {case_id}"
            else:
                case_ok = True
                case_msg = f"case {case_id}: {len(comments)} comments"
        except Exception as exc:
            case_msg = f"case read failed: {exc}"
        finally:
            registry.close()
    print(f"  [{'OK' if case_ok else 'FAIL'}] {case_msg}")

    print()
    print("  Policy:")
    policy_ok = True
    try:
        compiled = load_compiled_policy()
        for line in format_policy_summary(compiled):
            print(f"    {line}")
    except PolicyConfigError as exc:
        policy_ok = False
        print(f"    [FAIL] {exc}")

    all_ok = ok and mcp_ok and case_ok and policy_ok
    print()
    if all_ok:
        print("All checks passed. Run: python main.py --dry-run")
        return 0
    print("Some checks failed. Fix the items above, then re-run: python main.py --check")
    return 1
