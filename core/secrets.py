"""Enterprise secrets loading from mounted files (Vault / K8s Secret patterns)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from core.enterprise import secrets_section
from core.logging import log_info, log_warning


def load_secrets_from_files(config: Dict[str, Any]) -> None:
    """Inject env vars from file paths before LLM/MCP init.

    Config example::

        "secrets": {
          "env_from_files": {
            "GEMINI_API_KEY": "/run/secrets/gemini-api-key",
            "CASE_AGENT_WEBHOOK_URL": "/run/secrets/webhook-url"
          }
        }

    Existing environment variables are never overwritten.
    """
    mapping = secrets_section(config).get("env_from_files", {})
    if not isinstance(mapping, dict) or not mapping:
        return

    for env_key, raw_path in mapping.items():
        key = str(env_key).strip()
        path = Path(str(raw_path).strip())
        if not key or not str(raw_path).strip():
            continue
        if key in os.environ and os.environ[key].strip():
            continue
        if not path.is_file():
            log_warning("secret_file_missing", env_key=key, path=str(path))
            continue
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            log_warning("secret_file_read_failed", env_key=key, path=str(path), error=str(exc))
            continue
        if not value:
            log_warning("secret_file_empty", env_key=key, path=str(path))
            continue
        os.environ[key] = value
        log_info("secret_loaded_from_file", env_key=key, path=str(path))
