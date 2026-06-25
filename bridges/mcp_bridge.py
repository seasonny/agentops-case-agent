import json
import os
import subprocess
import threading
from typing import Any, Dict, List, Optional

from core.logging import log_info, log_warning


class MCPBridge:
    def __init__(
        self,
        mcp_command: List[str],
        *,
        env: Optional[Dict[str, str]] = None,
        provider_name: str = "default",
    ):
        self.mcp_command = mcp_command
        self.provider_name = provider_name
        self.proc = None
        self.request_id = 0
        self._stderr_lines: List[str] = []
        self._stderr_thread: Optional[threading.Thread] = None
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        try:
            self.proc = subprocess.Popen(
                mcp_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=proc_env,
            )
            self._start_stderr_drain()
            log_info(
                "mcp_started",
                provider=provider_name,
                command=mcp_command,
            )
            self._initialize_mcp()
        except FileNotFoundError:
            log_warning("mcp_start_failed", reason="command_not_found")
            self.proc = None
        except Exception as exc:
            log_warning("mcp_start_failed", error=str(exc))
            self.proc = None

    def _start_stderr_drain(self) -> None:
        if not self.proc or not self.proc.stderr:
            return

        def _drain() -> None:
            assert self.proc is not None and self.proc.stderr is not None
            for line in self.proc.stderr:
                cleaned = line.rstrip("\n")
                if cleaned:
                    self._stderr_lines.append(cleaned)
                    if len(self._stderr_lines) > 50:
                        self._stderr_lines.pop(0)

        self._stderr_thread = threading.Thread(target=_drain, daemon=True)
        self._stderr_thread.start()

    def _recent_stderr(self) -> str:
        if not self._stderr_lines:
            return ""
        return " | ".join(self._stderr_lines[-5:])

    def _read_json_response(self) -> Dict[str, Any]:
        if not self.proc or not self.proc.stdout:
            return {"error": "MCP server not started"}

        exit_code = self.proc.poll()
        if exit_code is not None:
            return {
                "error": (
                    f"MCP server exited (code {exit_code}). "
                    f"stderr: {self._recent_stderr() or '(empty)'}"
                )
            }

        non_json_lines: List[str] = []
        for _ in range(80):
            response_line = self.proc.stdout.readline()
            if not response_line:
                exit_code = self.proc.poll()
                if exit_code is not None:
                    return {
                        "error": (
                            f"MCP server closed stdout (code {exit_code}). "
                            f"stderr: {self._recent_stderr() or '(empty)'}"
                        )
                    }
                return {
                    "error": (
                        "No response from MCP server (empty stdout). "
                        f"stderr: {self._recent_stderr() or '(empty)'}"
                    )
                }
            stripped = response_line.strip()
            if not stripped:
                continue
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as exc:
                non_json_lines.append(stripped[:200])
                if len(non_json_lines) > 5:
                    non_json_lines.pop(0)
                # Some MCP tools print command output to stdout before final JSON-RPC response.
                # Keep reading instead of failing immediately on the first non-JSON line.
                continue

        noise = " | ".join(non_json_lines) if non_json_lines else "(none)"
        return {
            "error": (
                "No JSON response from MCP server after skipping blank/non-JSON lines. "
                f"stdout_noise={noise} stderr={self._recent_stderr() or '(empty)'}"
            )
        }

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        if not self.proc or not self.proc.stdin:
            return
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        self.proc.stdin.write(json.dumps(notification) + "\n")
        self.proc.stdin.flush()

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.proc:
            return {"error": "MCP server not started"}

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {},
        }

        try:
            self.proc.stdin.write(json.dumps(request) + "\n")
            self.proc.stdin.flush()
            response = self._read_json_response()
            if "error" in response and isinstance(response["error"], str):
                log_warning("mcp_request_failed", method=method, error=response["error"])
                return response

            skipped_responses: List[str] = []
            for _ in range(20):
                if not isinstance(response, dict):
                    return response
                response_id = response.get("id")
                # JSON-RPC response for this request
                if response_id == self.request_id:
                    return response
                # Some servers may omit id for success/error payloads.
                if response_id is None and ("result" in response or "error" in response):
                    return response

                skipped_responses.append(str(response_id))
                response = self._read_json_response()
                if "error" in response and isinstance(response["error"], str):
                    log_warning("mcp_request_failed", method=method, error=response["error"])
                    return response

            return {
                "error": (
                    "MCP response id mismatch; did not receive matching response id. "
                    f"request_id={self.request_id} seen={','.join(skipped_responses[:10]) or '(none)'}"
                )
            }
        except Exception as exc:
            log_warning(
                "mcp_request_failed",
                method=method,
                error=str(exc),
                stderr=self._recent_stderr() or None,
            )
            return {"error": str(exc)}

    def _initialize_mcp(self) -> None:
        response = self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentops-client", "version": "1.0.0"},
            },
        )
        server_info = response.get("result", {}).get("serverInfo", {})
        log_info("mcp_initialized", server=server_info)
        self._send_notification("notifications/initialized", {})

    def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.proc:
            return {"error": "MCP server not available"}

        response = self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": params},
        )
        if "result" in response:
            return response["result"]
        if "error" in response:
            return {"error": response["error"]}
        return response

    def list_tools(self) -> List[str]:
        if not self.proc:
            return []
        response = self._send_request("tools/list")
        tools = response.get("result", {}).get("tools", [])
        return [tool.get("name", "") for tool in tools if tool.get("name")]

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
