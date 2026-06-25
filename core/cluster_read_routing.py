"""Deterministic oc/kubectl get → cluster-read MCP tool mapping."""

from __future__ import annotations

import re
import shlex
from typing import List, Optional, Tuple

from core.dangerous_command_split import extract_request_lines
from core.mcp_action import MCPAction

_OC_GET = re.compile(r"^(?:oc|kubectl)\s+get\s+", re.I)

_POD_KINDS = frozenset({"pod", "pods", "po"})
_NODE_KINDS = frozenset({"node", "nodes", "no"})
_NAMESPACE_KINDS = frozenset({"namespace", "namespaces", "ns"})

# kind alias → (Kind, apiVersion)
_RESOURCE_KINDS: dict[str, Tuple[str, str]] = {
    "node": ("Node", "v1"),
    "nodes": ("Node", "v1"),
    "no": ("Node", "v1"),
    "pod": ("Pod", "v1"),
    "pods": ("Pod", "v1"),
    "po": ("Pod", "v1"),
    "service": ("Service", "v1"),
    "services": ("Service", "v1"),
    "svc": ("Service", "v1"),
    "deployment": ("Deployment", "apps/v1"),
    "deployments": ("Deployment", "apps/v1"),
    "deploy": ("Deployment", "apps/v1"),
    "configmap": ("ConfigMap", "v1"),
    "configmaps": ("ConfigMap", "v1"),
    "cm": ("ConfigMap", "v1"),
    "secret": ("Secret", "v1"),
    "secrets": ("Secret", "v1"),
    "namespace": ("Namespace", "v1"),
    "namespaces": ("Namespace", "v1"),
    "ns": ("Namespace", "v1"),
}


def _is_oc_get_line(line: str) -> bool:
    return bool(_OC_GET.match(line.strip()))


def is_cluster_read_only_request(text: str) -> bool:
    """True when extracted request lines are only oc/kubectl get (no shell diag)."""
    lines = extract_request_lines(text)
    if not lines:
        return False
    return all(_is_oc_get_line(line) for line in lines)


def _parse_namespace(argv: List[str]) -> str:
    for idx, token in enumerate(argv):
        if token in ("-n", "--namespace") and idx + 1 < len(argv):
            return argv[idx + 1]
        if token.startswith("--namespace="):
            return token.split("=", 1)[1]
    return ""


def _has_all_namespaces(argv: List[str]) -> bool:
    return "-A" in argv or "--all-namespaces" in argv


def infer_cluster_read_action(line: str) -> Optional[MCPAction]:
    stripped = line.strip().strip("`")
    if not _is_oc_get_line(stripped):
        return None

    try:
        argv = shlex.split(stripped)
    except ValueError:
        return None
    if len(argv) < 3:
        return None

    resource_tokens = [part for part in argv[2:] if not part.startswith("-")]
    if not resource_tokens:
        return None

    kind_token = resource_tokens[0].lower()
    namespace = _parse_namespace(argv)
    all_ns = _has_all_namespaces(argv)

    if kind_token in _POD_KINDS:
        args: dict = {}
        if all_ns:
            args["namespace"] = ""
        elif namespace:
            args["namespace"] = namespace
        return MCPAction(tool="pods_list", arguments=args, label=stripped)

    if kind_token in _NODE_KINDS:
        return MCPAction(
            tool="resources_list",
            arguments={"apiVersion": "v1", "kind": "Node"},
            label=stripped,
        )

    if kind_token in _NAMESPACE_KINDS:
        return MCPAction(tool="namespaces_list", arguments={}, label=stripped)

    mapped = _RESOURCE_KINDS.get(kind_token)
    if mapped:
        kind, api_version = mapped
        args = {"apiVersion": api_version, "kind": kind}
        if namespace:
            args["namespace"] = namespace
        return MCPAction(tool="resources_list", arguments=args, label=stripped)

    return None


def infer_cluster_read_actions(lines: List[str]) -> List[MCPAction]:
    actions: List[MCPAction] = []
    seen: set = set()
    for line in lines:
        action = infer_cluster_read_action(line)
        if action and action.label not in seen:
            seen.add(action.label)
            actions.append(action)
    return actions


def infer_cluster_read_actions_from_text(text: str) -> List[MCPAction]:
    return infer_cluster_read_actions(extract_request_lines(text))
