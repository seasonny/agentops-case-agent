"""Redact secrets before they reach logs, audit trails, or on-disk artifacts."""

import os
import re
from typing import Any, FrozenSet, List, Pattern, Tuple

_SENSITIVE_ENV_NAMES = (
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "RH_API_TOKEN",
    "REDHAT_API_TOKEN",
)

_SENSITIVE_FIELD_HINTS: FrozenSet[str] = frozenset({
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "bearer",
})

_REDACTION_PATTERNS: List[Tuple[Pattern[str], bool]] = [
    (re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"), False),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}\b"), False),
    (
        re.compile(
            r"(?i)((?:password|passwd|secret|api[_-]?key|bearer)\s*[:=]\s*)(\S{8,})"
        ),
        True,
    ),
    (re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END"), False),
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[A-Za-z0-9_-]+"), False),
    (re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)"), True),
]


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-2:]}({len(value)} chars)"


def _known_secret_values() -> List[str]:
    values: List[str] = []
    for name in _SENSITIVE_ENV_NAMES:
        val = os.getenv(name, "").strip()
        if len(val) >= 8:
            values.append(val)
    values.sort(key=len, reverse=True)
    return values


def _is_sensitive_field_name(key: str) -> bool:
    normalized = str(key or "").lower().replace("-", "_")
    if normalized in _SENSITIVE_FIELD_HINTS:
        return True
    return any(hint in normalized for hint in _SENSITIVE_FIELD_HINTS)


def redact_string(text: str) -> str:
    if not text:
        return text

    redacted = text
    for secret in _known_secret_values():
        redacted = redacted.replace(secret, _mask_secret(secret))

    for pattern, keep_prefix in _REDACTION_PATTERNS:
        if keep_prefix:
            redacted = pattern.sub(
                lambda match: f"{match.group(1)}{_mask_secret(match.group(2))}",
                redacted,
            )
        else:
            redacted = pattern.sub(lambda match: _mask_secret(match.group(0)), redacted)

    return redacted


def sanitize_for_log(value: Any) -> Any:
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return {
            key: _mask_secret(str(item)) if _is_sensitive_field_name(str(key)) and isinstance(item, str)
            else sanitize_for_log(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_for_log(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_log(item) for item in value)
    return value


# Alias for persistence paths (reports, agent memory, approvals).
sanitize_for_storage = sanitize_for_log
