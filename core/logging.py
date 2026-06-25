import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.redaction import sanitize_for_log


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("agentops")
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


logger = setup_logging()


def log_event(event: str, **fields: Any) -> None:
    payload: Dict[str, Any] = sanitize_for_log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    })
    logger.info(json.dumps(payload, ensure_ascii=False))


def log_info(message: str, **fields: Any) -> None:
    if fields:
        log_event(message, **fields)
    else:
        logger.info(message)


def log_warning(message: str, **fields: Any) -> None:
    if fields:
        log_event(message, level="warning", **fields)
    else:
        logger.warning(message)
