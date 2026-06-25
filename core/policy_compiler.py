"""Compile user-facing policy.yaml into runtime MCP policy rules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set

import yaml

from core.config import (
    POLICY_CAPABILITY_MAP_FILE,
    POLICY_FILE,
    POLICY_PROFILES_DIR,
)

DEFAULT_DANGEROUS_COMMANDS = [
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init",
    "rm -rf",
    "rm -r /",
    "mkfs",
    "format",
    "fdisk",
    "dd",
    "kill -9 1",
    "kill -KILL 1",
    "> /dev/sda",
]

KNOWN_PROFILES = ("minimal", "diagnostic", "enterprise")


class PolicyConfigError(FileNotFoundError):
    """Raised when config/policy.yaml is missing."""


@dataclass(frozen=True)
class CompiledPolicy:
    profile: str
    mode: str
    description: str
    capabilities: Dict[str, bool]
    capability_labels: Dict[str, str]
    blocked_tools: FrozenSet[str]
    allowed_tools: Optional[FrozenSet[str]]
    pods_exec_allowed_binaries: FrozenSet[str]
    host_exec_allowed_binaries: FrozenSet[str]
    upload_allowed_prefixes: List[str]
    dangerous_commands: List[str]
    dangerous_handling: str
    enabled_tool_count: int = 0


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _load_capability_map(path: Optional[Path] = None) -> Dict[str, Any]:
    data = _read_yaml(path or POLICY_CAPABILITY_MAP_FILE)
    capabilities = data.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    labels: Dict[str, str] = {}
    tools_by_cap: Dict[str, Set[str]] = {}
    for name, spec in capabilities.items():
        if not isinstance(spec, dict):
            continue
        labels[str(name)] = str(spec.get("label", name))
        raw_tools = spec.get("tools", [])
        if isinstance(raw_tools, list):
            tools_by_cap[str(name)] = {str(t).strip() for t in raw_tools if str(t).strip()}
        else:
            tools_by_cap[str(name)] = set()

    always_blocked = data.get("always_blocked_tools", [])
    if not isinstance(always_blocked, list):
        always_blocked = []

    exec_binaries = data.get("default_exec_binaries", [])
    if not isinstance(exec_binaries, list):
        exec_binaries = []

    return {
        "labels": labels,
        "tools_by_cap": tools_by_cap,
        "always_blocked_tools": {str(t).strip() for t in always_blocked if str(t).strip()},
        "default_exec_binaries": [str(b).strip() for b in exec_binaries if str(b).strip()],
    }


def _load_profile(name: str, profiles_dir: Optional[Path] = None) -> Dict[str, Any]:
    base = profiles_dir or POLICY_PROFILES_DIR
    path = base / f"{name}.yaml"
    data = _read_yaml(path)
    if not data and name != "diagnostic":
        return _load_profile("diagnostic", profiles_dir=profiles_dir)
    return data


def _merge_capabilities(
    profile_caps: Dict[str, Any],
    user_caps: Dict[str, Any],
    all_cap_names: Set[str],
) -> Dict[str, bool]:
    merged: Dict[str, bool] = {}
    for cap in sorted(all_cap_names):
        if cap in user_caps:
            merged[cap] = bool(user_caps[cap])
        elif cap in profile_caps:
            merged[cap] = bool(profile_caps[cap])
        else:
            merged[cap] = False
    return merged


def compile_policy(
    *,
    policy_path: Optional[Path] = None,
    capability_map_path: Optional[Path] = None,
    profiles_dir: Optional[Path] = None,
) -> CompiledPolicy:
    user = _read_yaml(policy_path or POLICY_FILE)
    cap_map = _load_capability_map(capability_map_path)

    profile_name = str(user.get("profile", "diagnostic")).strip() or "diagnostic"
    env_profile = os.environ.get("POLICY_PROFILE", "").strip()
    if env_profile:
        profile_name = env_profile
    if profile_name not in KNOWN_PROFILES:
        profile_name = "diagnostic"

    profile = _load_profile(profile_name, profiles_dir=profiles_dir)
    description = str(profile.get("description", "")).strip()

    mode_raw = user.get("mode")
    if isinstance(mode_raw, str) and mode_raw.strip():
        mode = mode_raw.strip().lower()
    else:
        mode = str(profile.get("mode_default", "denylist")).strip().lower() or "denylist"
    if mode not in ("allowlist", "denylist"):
        mode = "denylist"

    profile_caps = profile.get("capabilities", {})
    if not isinstance(profile_caps, dict):
        profile_caps = {}
    user_caps = user.get("capabilities", {})
    if not isinstance(user_caps, dict):
        user_caps = {}

    all_cap_names = set(cap_map["tools_by_cap"].keys())
    capabilities = _merge_capabilities(profile_caps, user_caps, all_cap_names)

    overrides = user.get("overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}

    extra_allow = overrides.get("allow_tools", [])
    extra_block = overrides.get("block_tools", [])
    if not isinstance(extra_allow, list):
        extra_allow = []
    if not isinstance(extra_block, list):
        extra_block = []

    always_blocked = set(cap_map["always_blocked_tools"])
    blocked_tools: Set[str] = set(always_blocked)
    allowed_tools: Optional[Set[str]] = None

    if mode == "allowlist":
        allowed_tools = set()
        for cap, enabled in capabilities.items():
            if enabled:
                allowed_tools.update(cap_map["tools_by_cap"].get(cap, set()))
        allowed_tools.update(str(t).strip() for t in extra_allow if str(t).strip())
        allowed_tools -= blocked_tools
        allowed_tools -= {str(t).strip() for t in extra_block if str(t).strip()}
    else:
        for cap, enabled in capabilities.items():
            if not enabled:
                blocked_tools.update(cap_map["tools_by_cap"].get(cap, set()))
        blocked_tools.update(str(t).strip() for t in extra_block if str(t).strip())

    exec_binaries = list(cap_map["default_exec_binaries"])
    extra_bins = overrides.get("exec_binaries", [])
    if isinstance(extra_bins, list):
        for item in extra_bins:
            value = str(item).strip()
            if value and value not in exec_binaries:
                exec_binaries.append(value)
    binary_set = frozenset(b.lower() for b in exec_binaries)

    upload_prefixes = profile.get("upload_path_prefixes", [])
    if not isinstance(upload_prefixes, list):
        upload_prefixes = []
    override_prefixes = overrides.get("upload_path_prefixes")
    if isinstance(override_prefixes, list):
        upload_prefixes = [str(p) for p in override_prefixes]

    dangerous = list(DEFAULT_DANGEROUS_COMMANDS)
    extra_dangerous = overrides.get("dangerous_commands", [])
    if isinstance(extra_dangerous, list):
        for item in extra_dangerous:
            value = str(item).strip()
            if value and value not in dangerous:
                dangerous.append(value)

    enabled_tool_count = len(allowed_tools) if allowed_tools is not None else 0

    handling_raw = user.get("dangerous_handling")
    if isinstance(handling_raw, str) and handling_raw.strip():
        dangerous_handling = handling_raw.strip().lower()
    else:
        dangerous_handling = (
            str(profile.get("dangerous_handling", "skip_and_continue")).strip().lower()
            or "skip_and_continue"
        )
    if dangerous_handling not in ("reject_all", "skip_and_continue"):
        dangerous_handling = "skip_and_continue"

    return CompiledPolicy(
        profile=profile_name,
        mode=mode,
        description=description,
        capabilities=capabilities,
        capability_labels=dict(cap_map["labels"]),
        blocked_tools=frozenset(blocked_tools),
        allowed_tools=frozenset(allowed_tools) if allowed_tools is not None else None,
        pods_exec_allowed_binaries=binary_set,
        host_exec_allowed_binaries=binary_set,
        upload_allowed_prefixes=list(upload_prefixes),
        dangerous_commands=dangerous,
        dangerous_handling=dangerous_handling,
        enabled_tool_count=enabled_tool_count,
    )


def load_compiled_policy(*, policy_path: Optional[Path] = None) -> CompiledPolicy:
    """Load and compile config/policy.yaml."""
    path = policy_path or POLICY_FILE
    if not path.exists():
        raise PolicyConfigError(
            f"缺少安全政策檔案：{path}\n"
            "請在 config/ 建立 policy.yaml，內容至少包含：profile: diagnostic\n"
            "說明見 docs/POLICY.md"
        )
    return compile_policy(policy_path=path)


def format_policy_summary(compiled: CompiledPolicy) -> List[str]:
    """Human-readable lines for --check output."""
    mode_label = "白名單（僅允許已開啟能力）" if compiled.mode == "allowlist" else "黑名單（預設允許，擋危險項）"
    lines = [
        f"Policy profile: {compiled.profile} — {compiled.description}",
        f"Mode: {compiled.mode} ({mode_label})",
        "Capabilities:",
    ]
    for cap, enabled in compiled.capabilities.items():
        label = compiled.capability_labels.get(cap, cap)
        mark = "ON " if enabled else "OFF"
        lines.append(f"  [{mark}] {label}")
    if compiled.mode == "allowlist":
        lines.append(f"Allowed MCP tools: {compiled.enabled_tool_count}")
    lines.append(f"Always blocked: {len(compiled.blocked_tools)} tools")
    lines.append(
        "Exec binaries: "
        + ", ".join(sorted(compiled.host_exec_allowed_binaries))
    )
    if compiled.upload_allowed_prefixes:
        lines.append(
            "Upload path prefixes: " + ", ".join(compiled.upload_allowed_prefixes)
        )
    else:
        lines.append("Upload path prefixes: (no restriction)")
    handling_label = (
        "跳過危險列、執行其餘"
        if compiled.dangerous_handling == "skip_and_continue"
        else "留言含危險指令則全部拒絕"
    )
    lines.append(f"Dangerous handling: {compiled.dangerous_handling} ({handling_label})")
    return lines


def policy_to_dict(compiled: CompiledPolicy) -> Dict[str, Any]:
    """Serialize compiled policy for --policy-dump."""
    return {
        "profile": compiled.profile,
        "mode": compiled.mode,
        "description": compiled.description,
        "capabilities": dict(compiled.capabilities),
        "blocked_tools": sorted(compiled.blocked_tools),
        "allowed_tools": sorted(compiled.allowed_tools) if compiled.allowed_tools else None,
        "pods_exec_allowed_binaries": sorted(compiled.pods_exec_allowed_binaries),
        "host_exec_allowed_binaries": sorted(compiled.host_exec_allowed_binaries),
        "upload_allowed_path_prefixes": list(compiled.upload_allowed_prefixes),
        "dangerous_commands": list(compiled.dangerous_commands),
        "dangerous_handling": compiled.dangerous_handling,
    }
