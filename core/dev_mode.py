import os


def is_dev_mode() -> bool:
    """Internal one-person testing (demo prefix, relaxed trigger). Not for customers."""
    return os.environ.get("AGENT_DEV_MODE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
