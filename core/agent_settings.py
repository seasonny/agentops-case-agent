"""Runtime agent settings loaded once from config (prefix, loop guard, case options)."""

from typing import Any, Dict

from core.constants import AGENT_REPLY_PREFIX

_settings: Dict[str, Any] = {
    "reply_prefix": AGENT_REPLY_PREFIX,
    "loop_guard_seconds": 1800,
    "comment_public": True,
}


def init_agent_settings(config: Dict[str, Any]) -> None:
    agent = config.get("agent", {})
    case = config.get("case", {})
    _settings["reply_prefix"] = str(
        agent.get("reply_prefix", AGENT_REPLY_PREFIX) or AGENT_REPLY_PREFIX
    )
    _settings["loop_guard_seconds"] = int(agent.get("loop_guard_seconds", 1800))
    _settings["comment_public"] = bool(case.get("comment_public", True))


def get_reply_prefix() -> str:
    return str(_settings.get("reply_prefix", AGENT_REPLY_PREFIX))


def get_loop_guard_seconds() -> int:
    return int(_settings.get("loop_guard_seconds", 1800))


def is_comment_public() -> bool:
    return bool(_settings.get("comment_public", True))
