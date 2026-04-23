"""
Utility functions for Jules Tracker Agent.
"""
import os
from typing import Any


def extract_repository_name(session: dict[str, Any]) -> str:
    """Extract owner/repo from the Jules source context when available."""
    source = session.get("sourceContext", {}).get("source", "")
    prefix = "sources/github/"
    if source.startswith(prefix):
        return source[len(prefix):]
    return source


def get_pending_question(
    session: dict[str, Any],
    activities: list[dict[str, Any]],
) -> str | None:
    """Return the latest unanswered Jules message for the session."""
    ordered_activities = sorted(activities, key=lambda activity: activity.get("createTime", ""))
    last_user_reply_index = -1
    pending_question: str | None = None

    for index, activity in enumerate(ordered_activities):
        if "userMessaged" in activity:
            last_user_reply_index = index
            pending_question = None
            continue

        message = activity.get("agentMessaged", {}).get("agentMessage", "").strip()
        if message and index > last_user_reply_index:
            pending_question = message

    if pending_question:
        return pending_question

    status_message = (session.get("statusMessage") or "").strip()
    if session.get("state", session.get("status")) == "AWAITING_USER_FEEDBACK" and status_message:
        return status_message

    return None


def format_question_description(
    repository: str,
    session_id: str,
    question_text: str,
) -> str:
    """Build a readable label that makes the repository obvious in logs/results."""
    return f"[{repository}] session {session_id}: {question_text}"


def colorize(text: str, color: str, reset_color: str = "\033[0m") -> str:
    """Colorize terminal output unless explicitly disabled."""
    if os.getenv("NO_COLOR"):
        return text
    return f"{color}{text}{reset_color}"


def format_question_log(
    repository: str,
    session_id: str,
    session_url: str,
    question_text: str,
    question_color: str,
    reset_color: str = "\033[0m",
) -> str:
    """Build a multi-line log entry with the key session details."""
    return (
        "Found pending question\n"
        f"  Repository: {repository}\n"
        f"  Session: {session_id}\n"
        f"  URL: {session_url}\n"
        f"  Question: {colorize(question_text, question_color, reset_color)}"
    )


def format_answer_log(answer: str, answer_color: str, reset_color: str = "\033[0m") -> str:
    """Build a colored answer log block."""
    return f"Generated answer\n  LLM: {colorize(answer, answer_color, reset_color)}"


def send_telegram_update(
    telegram: Any,
    repository: str,
    session_id: str,
    session_url: str,
    question_text: str,
    answer: str,
) -> None:
    """Forward the Jules question and LLM answer to Telegram."""
    esc = telegram.escape
    lines = [
        "🔍 *JULES TRACKER UPDATE*",
        f"🏢 *Repositorio:* `{esc(repository)}`",
        f"🆔 *Sessão:* `{esc(session_id)}`",
        "─" * 20,
        f"❓ *Pergunta do Jules:*\n_{esc(question_text)}_",
        "─" * 20,
        f"🤖 *Resposta sugerida (AI):*\n{esc(answer)}",
    ]
    inline_keyboard = {
        "inline_keyboard": [[{"text": "🔗 Acompanhar Sessão", "url": session_url}]]
    }
    telegram.send_message("\n".join(lines), parse_mode="MarkdownV2", reply_markup=inline_keyboard)
