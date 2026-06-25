import logging
import os
import unittest

from core.logging import log_event
from core.redaction import redact_string, sanitize_for_log
from tests.safe_test_data import (
    FAKE_BEARER_TOKEN,
    FAKE_GEMINI_KEY,
    FAKE_OPENAI_KEY,
    FAKE_SECRET_VALUE,
)


class TestRedaction(unittest.TestCase):
    def test_redacts_openai_key_pattern(self):
        raw = f"failed: invalid key {FAKE_OPENAI_KEY}"
        redacted = redact_string(raw)
        self.assertNotIn(FAKE_OPENAI_KEY, redacted)
        self.assertIn("…", redacted)

    def test_redacts_gemini_key_pattern(self):
        raw = f"key={FAKE_GEMINI_KEY}"
        redacted = redact_string(raw)
        self.assertNotIn(FAKE_GEMINI_KEY, redacted)

    def test_redacts_known_env_value(self):
        secret = FAKE_SECRET_VALUE
        os.environ["GEMINI_API_KEY"] = secret
        try:
            redacted = redact_string(f"error while calling api with {secret}")
            self.assertNotIn(secret, redacted)
            self.assertIn("fake…78", redacted)
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_redacts_bearer_token(self):
        raw = f"Authorization: Bearer {FAKE_BEARER_TOKEN}"
        redacted = redact_string(raw)
        self.assertNotIn(FAKE_BEARER_TOKEN.split(".")[0], redacted)

    def test_sanitize_sensitive_dict_fields(self):
        payload = sanitize_for_log(
            {"tool": "x", "arguments": {"api_key": "super-secret-value", "case-number": "01234567"}}
        )
        self.assertNotIn("super-secret-value", str(payload))
        self.assertEqual(payload["arguments"]["case-number"], "01234567")

    def test_log_event_applies_redaction(self):
        secret = FAKE_OPENAI_KEY
        captured = {}

        class _CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured["line"] = record.getMessage()

        import logging as _logging
        from core import logging as agent_logging

        handler = _CaptureHandler()
        agent_logging.logger.addHandler(handler)
        try:
            log_event("test_redaction", error=secret, detail=f"bearer {secret}")
        finally:
            agent_logging.logger.removeHandler(handler)

        line = captured.get("line", "")
        self.assertNotIn(secret, line)


if __name__ == "__main__":
    unittest.main()
