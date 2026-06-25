"""Synthetic fixtures for tests — never use real case IDs, emails, or API keys."""

SAFE_CASE_ID = "00000000"
SAFE_COMMENT_ID = 99
SAFE_SUPPORT_AUTHOR = "support@example.test"
SAFE_AGENT_AUTHOR = "agent@example.test"

# Clearly fake keys that still match redaction patterns.
FAKE_OPENAI_KEY = "sk-" + "f" * 30
FAKE_GEMINI_KEY = "AIzaSy" + "F" * 33
FAKE_BEARER_TOKEN = (
    "eyJ" + "a" * 20 + "." + "b" * 20 + ".FAKE_TEST_SIGNATURE"
)
FAKE_SECRET_VALUE = "fake-test-secret-not-real-12345678"
