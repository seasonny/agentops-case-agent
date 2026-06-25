from typing import Any, Dict, List

from core.comments import is_agent_reply, normalize_comment_text, sort_comments_chronologically
from core.constants import AGENT_REPLY_PREFIX


def format_comment_line(comment: Dict[str, Any], *, max_chars: int = 600) -> str:
    author = normalize_comment_text(comment.get("author", "unknown"))
    content = normalize_comment_text(comment.get("content", ""))
    if len(content) > max_chars:
        content = content[: max_chars - 3] + "..."
    if is_agent_reply(comment):
        label = "Agent"
    else:
        resolved = comment.get("resolved_role")
        label = f"{author} [{resolved}]" if resolved else author
    return f"[#{comment.get('id', '?')}] {label}:\n{content}"


def build_case_history(
    comments: List[Dict[str, Any]],
    *,
    max_comments: int = 12,
    max_chars_per_comment: int = 600,
) -> str:
    if not comments:
        return "(no prior comments)"

    sorted_comments = sort_comments_chronologically(comments)
    recent = sorted_comments[-max_comments:]
    lines = [format_comment_line(c, max_chars=max_chars_per_comment) for c in recent]
    return "\n\n---\n\n".join(lines)


def truncate_for_prompt(text: str, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...(truncated)"
