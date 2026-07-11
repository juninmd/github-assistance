"""
Utility functions for Jules Tracker Agent.
"""

import os
import re
from typing import Any

from src.notifications.telegram import TelegramNotifier

OPEN_PR_INSTRUCTION = "Ao finalizar, abra o pull request."
DEFAULT_UNBLOCKING_ANSWER = (
    "Pode prosseguir com seu melhor julgamento técnico. "
    "Use defaults seguros, mantenha o escopo pequeno, rode as validações aplicáveis "
    "e documente qualquer limitação."
)


def extract_repository_name(session: dict[str, Any]) -> str:
    """Extract owner/repo from the Jules source context when available."""
    source = session.get("sourceContext", {}).get("source", "")
    prefix = "sources/github/"
    if source.startswith(prefix):
        return source[len(prefix) :]
    return source


def get_pending_question(
    session: dict[str, Any],
    activities: list[dict[str, Any]],
) -> str | None:
    """Return the latest unanswered Jules message for the session."""
    ordered_activities = sorted(
        activities,
        key=lambda a: a.get("createTime") or a.get("updateTime") or "",
    )
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


def latest_activity_is_user_reply(activities: list[dict[str, Any]]) -> bool:
    """Return True when the newest activity is already a user reply."""
    if not activities:
        return False
    latest = max(
        activities,
        key=lambda a: a.get("createTime") or a.get("updateTime") or "",
    )
    return "userMessaged" in latest


def ensure_open_pr_request(message: str) -> str:
    """Guarantee every AI-authored Jules reply asks for a pull request."""
    normalized = str(message).strip()
    if "pull request" in normalized.lower() or re.search(r"\bpr\b", normalized, flags=re.IGNORECASE):
        return normalized
    if not normalized:
        return OPEN_PR_INSTRUCTION
    return f"{normalized}\n\n{OPEN_PR_INSTRUCTION}"


def is_plan_pending(activities: list[dict[str, Any]]) -> bool:
    """Check whether a plan was generated but not yet approved.

    Live API observation (2026-07-09): the only session states ever returned
    are IN_PROGRESS, AWAITING_USER_FEEDBACK, COMPLETED, FAILED. No
    AWAITING_PLAN_APPROVAL state exists — plans are auto-approved within
    seconds. This function detects the rare edge case where planGenerated
    exists without a following planApproved activity.
    """
    has_plan = False
    for a in activities:
        if "planGenerated" in a:
            has_plan = True
        elif "planApproved" in a:
            has_plan = False
    return has_plan


def get_pending_plan(activities: list[dict[str, Any]]) -> str | None:
    """Return the latest plan text awaiting approval, if any."""
    ordered_activities = sorted(
        activities,
        key=lambda a: a.get("createTime") or a.get("updateTime") or "",
    )
    plan_text: str | None = None
    for activity in ordered_activities:
        plan_generated = activity.get("planGenerated")
        if plan_generated:
            steps = plan_generated.get("planDescription") or plan_generated.get("steps")
            plan_text = steps if isinstance(steps, str) else str(steps) if steps else plan_text
        elif "planApproved" in activity:
            plan_text = None
    return plan_text


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


def send_plan_telegram_update(
    telegram: TelegramNotifier,
    repository: str,
    session_id: str,
    session_url: str,
    plan_text: str,
    decision: str,
) -> None:
    """Forward the Jules plan review decision to Telegram via HTML."""
    esc = telegram.escape_html
    lines = [
        "📋 <b>JULES TRACKER — REVISÃO DE PLANO</b>",
        f"🏢 <b>Repositório:</b> <code>{esc(repository)}</code>",
        f"🆔 <b>Sessão:</b> <code>{esc(session_id)}</code>",
        "─" * 20,
        f"📝 <b>Plano:</b>\n{esc(plan_text[:1000])}",
        "─" * 20,
        f"🤖 <b>Decisão (AI):</b> {esc(decision)}",
    ]
    kwargs: dict[str, Any] = {"parse_mode": "HTML"}
    if session_url:
        kwargs["reply_markup"] = {
            "inline_keyboard": [[{"text": "🔗 Acompanhar Sessão", "url": session_url}]],
        }
    telegram.send_message("\n".join(lines), **kwargs)


def send_telegram_update(
    telegram: TelegramNotifier,
    repository: str,
    session_id: str,
    session_url: str,
    question_text: str,
    answer: str,
) -> None:
    """Forward the Jules question and LLM answer to Telegram via HTML."""
    esc = telegram.escape_html
    lines = [
        "🔍 <b>JULES TRACKER UPDATE</b>",
        f"🏢 <b>Repositório:</b> <code>{esc(repository)}</code>",
        f"🆔 <b>Sessão:</b> <code>{esc(session_id)}</code>",
        "─" * 20,
        f"❓ <b>Pergunta do Jules:</b>\n{esc(question_text)}",
        "─" * 20,
        f"🤖 <b>Resposta sugerida (AI):</b>\n{esc(answer)}",
    ]
    kwargs: dict[str, Any] = {"parse_mode": "HTML"}
    if session_url:
        kwargs["reply_markup"] = {
            "inline_keyboard": [[{"text": "🔗 Acompanhar Sessão", "url": session_url}]],
        }
    telegram.send_message("\n".join(lines), **kwargs)
