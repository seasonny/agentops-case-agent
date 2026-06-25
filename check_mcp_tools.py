#!/usr/bin/env python3
"""Diagnostic utility to list MCP server tools for all configured providers."""

import json
import os
import subprocess
import sys

from core.config import iter_mcp_provider_specs, load_config


def _list_tools_for_provider(name: str, command: list, env: dict) -> None:
    print(f"\n=== Provider: {name} ===")
    print(f"Command: {command}")
    if env:
        print(f"Env: { {k: env[k] for k in sorted(env)} }")

    proc_env = os.environ.copy()
    proc_env.update(env)
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=proc_env,
        )
    except FileNotFoundError:
        print("ERROR: command not found")
        return

    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "check-tools", "version": "1.0.0"},
        },
    }
    proc.stdin.write(json.dumps(init_request) + "\n")
    proc.stdin.flush()
    proc.stdout.readline()

    proc.stdin.write(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        + "\n"
    )
    proc.stdin.flush()

    list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    proc.stdin.write(json.dumps(list_request) + "\n")
    proc.stdin.flush()

    response_line = proc.stdout.readline()
    if not response_line:
        print("No response")
        proc.terminate()
        return

    response = json.loads(response_line)
    tools = response.get("result", {}).get("tools", [])
    if not tools:
        print("No tools found")
    else:
        print(f"Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.get('name', 'UNKNOWN')}")
            schema = tool.get("inputSchema", {})
            props = schema.get("properties", {})
            if props:
                print(f"    args: {', '.join(sorted(props.keys()))}")

    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def main() -> None:
    config = load_config()
    providers = iter_mcp_provider_specs(config)
    if not providers:
        print("No MCP providers configured.")
        sys.exit(1)

    print("Checking MCP server tools...")
    for name, spec in providers.items():
        command = spec.get("command")
        args = spec.get("args", [])
        env = spec.get("env", {})
        if not command:
            continue
        _list_tools_for_provider(name, [command, *args], env)


if __name__ == "__main__":
    main()
