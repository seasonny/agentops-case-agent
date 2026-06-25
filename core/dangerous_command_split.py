"""Split support requests into safe vs dangerous command lines."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Set, Tuple

from core.comments import normalize_comment_text

DangerousCheck = Callable[[str], Tuple[bool, str]]

REQUEST_MARKERS = (
    "請執行",
    "請運行",
    "請跑",
    "plz run",
    "please run",
    "run the following",
    "execute the following",
)

COMMAND_LINE_PATTERN = re.compile(
    r"^\s*(?:"
    r"oc\s+|kubectl\s+|"
    r"nslookup|ping|dig|host|traceroute|curl|"
    r"reboot|shutdown|poweroff|halt|init|"
    r"rm\s+|mkfs|fdisk|dd|format"
    r")\b",
    re.I,
)


@dataclass
class DangerousSplitResult:
    blocked_lines: List[str] = field(default_factory=list)
    safe_lines: List[str] = field(default_factory=list)
    safe_text: str = ""
    reject_entire: bool = False


def _add_line(lines: List[str], seen: Set[str], candidate: str) -> None:
    line = candidate.strip().strip("`")
    if not line or line.startswith("#"):
        return
    if line not in seen:
        seen.add(line)
        lines.append(line)


def extract_request_lines(text: str) -> List[str]:
    """Extract likely command lines from a support comment."""
    normalized = normalize_comment_text(text)
    if not normalized:
        return []

    lines: List[str] = []
    seen: Set[str] = set()

    for block in re.finditer(r"```[^\n]*\n(.*?)```", normalized, re.S):
        for raw in block.group(1).splitlines():
            _add_line(lines, seen, raw)

    lowered = normalized.lower()
    marker_hit = any(marker in lowered for marker in REQUEST_MARKERS)
    after_marker = False
    for raw in normalized.splitlines():
        stripped = raw.strip()
        if not stripped:
            if after_marker and lines:
                break
            continue
        line_lower = stripped.lower()
        if any(marker in line_lower for marker in REQUEST_MARKERS):
            after_marker = True
            continue
        if after_marker:
            _add_line(lines, seen, stripped)
            continue
        if COMMAND_LINE_PATTERN.match(stripped):
            _add_line(lines, seen, stripped)

    if not lines and marker_hit:
        for raw in normalized.splitlines():
            stripped = raw.strip()
            if stripped and not any(marker in stripped.lower() for marker in REQUEST_MARKERS):
                _add_line(lines, seen, stripped)

    return lines


def build_safe_text(original: str, blocked_lines: List[str]) -> str:
    blocked = {line.strip() for line in blocked_lines}
    kept: List[str] = []
    for raw in original.splitlines():
        if raw.strip() not in blocked:
            kept.append(raw)
    return "\n".join(kept).strip()


def split_comment_requests(
    text: str,
    is_dangerous: DangerousCheck,
    *,
    dangerous_handling: str = "skip_and_continue",
) -> DangerousSplitResult:
    """Classify request lines; decide whether to reject the entire comment."""
    normalized = normalize_comment_text(text)
    handling = (dangerous_handling or "skip_and_continue").strip().lower()
    if handling not in ("reject_all", "skip_and_continue"):
        handling = "skip_and_continue"

    request_lines = extract_request_lines(normalized)
    if not request_lines:
        is_bad, _ = is_dangerous(normalized)
        if is_bad:
            return DangerousSplitResult(
                blocked_lines=[normalized],
                safe_lines=[],
                safe_text="",
                reject_entire=True,
            )
        return DangerousSplitResult(safe_text=normalized)

    blocked: List[str] = []
    safe: List[str] = []
    for line in request_lines:
        bad, _ = is_dangerous(line)
        if bad:
            blocked.append(line)
        else:
            safe.append(line)

    if not blocked:
        return DangerousSplitResult(safe_lines=request_lines, safe_text=normalized)

    if handling == "reject_all":
        return DangerousSplitResult(
            blocked_lines=blocked,
            safe_lines=safe,
            safe_text="",
            reject_entire=True,
        )

    if not safe:
        return DangerousSplitResult(
            blocked_lines=blocked,
            safe_lines=[],
            safe_text="",
            reject_entire=True,
        )

    return DangerousSplitResult(
        blocked_lines=blocked,
        safe_lines=safe,
        safe_text=build_safe_text(normalized, blocked),
        reject_entire=False,
    )
