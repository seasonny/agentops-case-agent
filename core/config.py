import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.constants import DEFAULT_MCP_CONFIG
from core.mcp_discovery import apply_mcp_auto_discovery

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "agent_config.json"
LOCAL_CONFIG_FILE = CONFIG_DIR / "local.json"
MINIMAL_CONFIG_FILE = CONFIG_DIR / "agent_config.minimal.json"
POLICY_FILE = CONFIG_DIR / "policy.yaml"
POLICY_PROFILES_DIR = CONFIG_DIR / "policy_profiles"
POLICY_CAPABILITY_MAP_FILE = CONFIG_DIR / "policy_capability_map.yaml"
ANALYZE_PROMPT_FILE = CONFIG_DIR / "prompts" / "analyze_comment.txt"
COMPOSE_PROMPT_FILE = CONFIG_DIR / "prompts" / "compose_reply.txt"
COLLABORATE_PROMPT_FILE = CONFIG_DIR / "prompts" / "collaborate_support.txt"
INTERPRET_PROMPT_FILE = CONFIG_DIR / "prompts" / "interpret_results.txt"
CONVERGENCE_PROMPT_FILE = CONFIG_DIR / "prompts" / "assess_convergence.txt"
MEMORY_FILE = PROJECT_ROOT / "agent_memory.json"
DOTENV_FILE = PROJECT_ROOT / ".env"

# Legacy path for backward compatibility (MCP OAuth only — not user settings)
LEGACY_CONFIG_FILE = PROJECT_ROOT / "agent_config.json"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_dotenv(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (does not override existing)."""
    env_path = path or DOTENV_FILE
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


def default_config() -> Dict[str, Any]:
    """Product defaults — customers normally do not edit these."""
    return {
        "case_id": "",
        "polling": {
            "interval_seconds": 10,
            "cooldown_after_reply_seconds": 45,
        },
        "limits": {
            "max_replies_per_session": 20,
            "max_reply_chars": 4000,
        },
        "guardrails": {
            "reply": {
                "max_chars": 4000,
                "block_sensitive_patterns": True,
                "block_dangerous_commands": True,
                "block_ungrounded_execution_output": True,
            },
        },
        "llm": {
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite",
            "api_key_env": "GEMINI_API_KEY",
            "temperature": 0,
        },
        "execution": {
            "max_output_chars": 8000,
        },
        "diagnostics": {
            "pods_exec": {
                "namespace": "",
                "pod": "",
            },
            "bundle_output": {
                "mode": "off",
                "filename": "auto",
                "directory": "diag-output",
                "overflow_chars": 3500,
            },
        },
        "participants": {
            "customer_authors": [],
            "support_authors": [],
            "support_author_patterns": ["*@redhat.com", "Red Hat*"],
            "customer_author_patterns": [],
            "ignore_authors": ["Automated Support"],
        },
        "trigger": {
            "mode": "production",
            "ignore_customer_comments": True,
            "trigger_on_roles": ["support"],
        },
        "agent": {
            "reply_prefix": "【AI 運維代理自動通知】",
            "loop_guard_seconds": 1800,
        },
        "case": {
            "comment_public": True,
        },
        "enterprise": {
            "audit_trail": True,
        },
        "outage": {
            "enabled": False,
            "interval_seconds": 5,
            "notify_webhook_url_env": "CASE_AGENT_WEBHOOK_URL",
            "notify_on": [
                "reply_posted",
                "policy_blocked",
                "approval_required",
                "clarify",
            ],
        },
        "approval": {
            "enabled": False,
            "required_tools": [
                "oc_adm_must_gather",
                "pods_exec",
                "upload_attachment_rh_portal",
            ],
        },
        "case_context": {
            "track_diagnostics": True,
            "max_items": 50,
        },
        "secrets": {
            "env_from_files": {},
        },
        "tenant": {
            "id": "",
            "label": "",
            "policy_profile": "",
        },
        "mcp_providers": {},
    }


def _load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    case_id = os.environ.get("CASE_ID", "").strip()
    if case_id:
        config["case_id"] = case_id

    llm = config.setdefault("llm", {})
    for key, env_name in (
        ("provider", "LLM_PROVIDER"),
        ("model", "LLM_MODEL"),
        ("api_key_env", "LLM_API_KEY_ENV"),
    ):
        value = os.environ.get(env_name, "").strip()
        if value:
            llm[key] = value

    tenant = config.setdefault("tenant", {})
    tenant_profile = str(tenant.get("policy_profile", "") or "").strip()
    env_profile = os.environ.get("POLICY_PROFILE", "").strip()
    if env_profile:
        tenant["policy_profile"] = env_profile
    elif tenant_profile and "POLICY_PROFILE" not in os.environ:
        os.environ["POLICY_PROFILE"] = tenant_profile

    return config


def load_config() -> Dict[str, Any]:
    """Merge defaults → user config → local overrides → env → MCP auto-discovery."""
    load_dotenv()
    config = default_config()

    user_loaded = _load_json_file(CONFIG_FILE)
    if user_loaded:
        config = _deep_merge(config, user_loaded)
    else:
        legacy = _load_json_file(LEGACY_CONFIG_FILE)
        if legacy and legacy.get("case_id"):
            config = _deep_merge(config, legacy)

    local = _load_json_file(LOCAL_CONFIG_FILE)
    if local:
        config = _deep_merge(config, local)

    config = _apply_env_overrides(config)
    from core.secrets import load_secrets_from_files

    load_secrets_from_files(config)
    config = apply_mcp_auto_discovery(config)
    return config


def get_mcp_command(config: Dict[str, Any]) -> List[str]:
    """Legacy: return platform/kubernetes MCP argv."""
    providers = iter_mcp_provider_specs(config)
    for key in ("platform", "kubernetes", "case", "cluster"):
        spec = providers.get(key)
        if spec and spec.get("command"):
            args = spec.get("args", [])
            if not isinstance(args, list):
                args = []
            return [spec["command"], *args]

    server = config.get("mcpServers", {}).get("kubernetes", {})
    command = server.get("command")
    args = server.get("args", [])
    if command and isinstance(args, list):
        return [command, *args]
    fallback = DEFAULT_MCP_CONFIG["mcpServers"]["kubernetes"]
    return [fallback["command"], *fallback["args"]]


def iter_mcp_provider_specs(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Normalize mcp_providers with backward-compatible mcpServers.kubernetes."""
    raw = config.get("mcp_providers")
    if isinstance(raw, dict) and raw:
        specs: Dict[str, Dict[str, Any]] = {}
        for name, spec in raw.items():
            if not isinstance(spec, dict):
                continue
            command = spec.get("command")
            if not command:
                continue
            args = spec.get("args", [])
            if not isinstance(args, list):
                args = []
            specs[str(name)] = {
                "command": command,
                "args": args,
                "env": spec.get("env", {}) if isinstance(spec.get("env"), dict) else {},
                "tool_map": (
                    spec.get("tool_map", {})
                    if isinstance(spec.get("tool_map"), dict)
                    else {}
                ),
                "tools": spec.get("tools", []) if isinstance(spec.get("tools"), list) else [],
            }
        return specs

    server = config.get("mcpServers", {}).get("kubernetes", {})
    command = server.get("command")
    if not command:
        return {}
    args = server.get("args", [])
    if not isinstance(args, list):
        args = []
    return {
        "platform": {
            "command": command,
            "args": args,
            "env": {},
            "tool_map": {},
            "tools": [],
        }
    }
