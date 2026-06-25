"""Human-readable explanations for blocked dangerous commands."""

from __future__ import annotations

from typing import List, Tuple

from core.mcp_policy import MCPPolicyChecker

# matched keyword -> (reason, safer alternative hint)
_DANGEROUS_HINTS: dict[str, Tuple[str, str]] = {
    "reboot": (
        "屬於危險系統操作，可能導致節點或整機重新開機而不可用",
        "若需重啟 workload，可改用 `oc rollout restart`；若需維護節點，可改用 `oc adm drain` 後再請人工 reboot。",
    ),
    "shutdown": (
        "屬於危險關機操作，可能中斷叢集服務",
        "請說明要關閉的對象與目的，我們可協助評估較安全的維護步驟。",
    ),
    "poweroff": (
        "屬於危險關機操作，可能中斷叢集服務",
        "請說明要關閉的對象與目的，我們可協助評估較安全的維護步驟。",
    ),
    "halt": (
        "屬於危險關機操作，可能中斷叢集服務",
        "請說明要關閉的對象與目的，我們可協助評估較安全的維護步驟。",
    ),
    "rm -rf": (
        "屬於破壞性刪除操作，可能移除重要資料",
        "請改提供需檢查的具體路徑或改用唯讀排查（如 `ls`、`oc get`）。",
    ),
    "rm -r /": (
        "屬於破壞性刪除操作，可能移除系統檔案",
        "請改提供需檢查的具體路徑或改用唯讀排查。",
    ),
    "mkfs": (
        "屬於格式化磁碟操作，可能破壞資料",
        "請說明磁碟排查目的，我們可協助以唯讀方式收集資訊。",
    ),
    "dd": (
        "屬於低階磁碟寫入操作，可能破壞資料",
        "請說明實際需求，避免直接對區塊裝置寫入。",
    ),
    "fdisk": (
        "屬於磁碟分割變更操作",
        "請改以唯讀方式提供 partition / PV 資訊。",
    ),
}

_DEFAULT_REASON = "屬於安全政策禁止的危險系統操作，Agent 無法代為執行"
_DEFAULT_ALTERNATIVE = (
    "請說明實際排查或維護目的，我們可建議較安全的替代指令（例如 `oc get`、`oc describe`、`oc logs`）。"
)


def _hints_for_match(matched: str) -> Tuple[str, str]:
    needle = matched.lower().strip()
    if needle in _DANGEROUS_HINTS:
        return _DANGEROUS_HINTS[needle]
    for key, value in _DANGEROUS_HINTS.items():
        if key in needle:
            return value
    return _DEFAULT_REASON, _DEFAULT_ALTERNATIVE


def explain_blocked_command(command: str, policy: MCPPolicyChecker) -> str:
    """One bullet explaining why a single command line was not executed."""
    _, matched = policy.is_dangerous_command(command)
    keyword = matched or command.strip()
    reason, alternative = _hints_for_match(keyword)
    return (
        f"- `{command.strip()}`：{reason}"
        f"（政策關鍵字：`{keyword}`）。{alternative}"
    )


def format_blocked_commands_section(
    blocked_commands: List[str],
    policy: MCPPolicyChecker,
) -> str:
    """Deterministic section to prepend when some lines were skipped."""
    lines = [
        str(cmd).strip()
        for cmd in blocked_commands
        if str(cmd).strip()
    ]
    if not lines:
        return ""

    bullets = [explain_blocked_command(cmd, policy) for cmd in lines]
    body = "\n".join(bullets)
    return (
        "以下指令未執行（安全政策攔截）：\n"
        f"{body}\n"
    )


def merge_blocked_explanation(reply: str, blocked_section: str) -> str:
    """Ensure blocked explanation appears after the reply prefix."""
    if not blocked_section.strip():
        return reply
    if blocked_section.strip() in reply:
        return reply

    from core.agent_settings import get_reply_prefix

    prefix = get_reply_prefix()
    stripped = reply.strip()
    if stripped.startswith(prefix):
        rest = stripped[len(prefix) :].lstrip("\n")
        return f"{prefix}\n{blocked_section}\n{rest}"
    return f"{blocked_section}\n{stripped}"
