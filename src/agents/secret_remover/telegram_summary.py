"""
Telegram summary helpers for the Secret Remover Agent.
"""
from typing import Any

from src.notifications.telegram import TelegramNotifier


def build_finding_message(
    repo_name: str,
    finding: dict[str, Any],
    original_line: str,
    action: str,
    commit_url: str,
    file_line_url: str,
    repo_url: str,
    telegram: TelegramNotifier,
) -> str:
    """Build a rich Telegram message for a single secret finding."""
    esc = telegram.escape_html
    file_path = finding.get("file", "unknown")
    line = finding.get("line", 0)
    reason = finding.get("_reason", "No reason provided")
    action_emoji = "🔥" if action == "REMOVE_FROM_HISTORY" else "✅"
    action_label = "Removida do Histórico" if action == "REMOVE_FROM_HISTORY" else "Falso Positivo (Ignorado)"

    redacted_preview = esc(original_line[:200]) if original_line else "<i>não disponível</i>"

    return (
        f"{action_emoji} <b>Secret {action_label}</b>\n\n"
        f"📦 Repositório: <code>{esc(repo_name)}</code>\n"
        f"📄 Arquivo: <code>{esc(file_path)}</code> (Linha {line})\n"
        f"🤖 Motivo: <i>{esc(reason)}</i>\n\n"
        f"📝 <b>Conteúdo original (redactado):</b>\n<code>{redacted_preview}</code>"
    )


def get_finding_buttons(
    repo_url: str,
    commit_url: str,
    file_line_url: str,
) -> list[list[dict]]:
    """Return inline keyboard buttons for the finding."""
    return [
        [
            {"text": "🔗 Repositório", "url": repo_url},
            {"text": "📌 Commit", "url": commit_url},
        ],
        [
            {"text": "📄 Arquivo+Linha", "url": file_line_url},
        ],
    ]


def send_finding_notification(
    telegram: TelegramNotifier,
    repo_name: str,
    finding: dict[str, Any],
    action: str,
    original_line: str,
    commit_url: str,
    file_line_url: str,
    repo_url: str,
) -> None:
    """Send a rich Telegram notification for a secret finding."""
    text = build_finding_message(
        repo_name=repo_name,
        finding=finding,
        original_line=original_line,
        action=action,
        commit_url=commit_url,
        file_line_url=file_line_url,
        repo_url=repo_url,
        telegram=telegram,
    )
    buttons = get_finding_buttons(repo_url, commit_url, file_line_url)
    reply_markup = {"inline_keyboard": buttons}
    telegram.send_message(text, parse_mode="HTML", reply_markup=reply_markup)


def send_error_notification(
    telegram: TelegramNotifier,
    target_owner: str,
    error_message: str,
) -> None:
    """Send a plain error notification via Telegram."""
    esc = telegram.escape_html
    text = (
        "🔐 <b>Secret Remover — Erro</b>\n\n"
        f"❌ {esc(error_message)}\n\n"
        f"👤 Owner: <code>{esc(target_owner)}</code>"
    )
    telegram.send_message(text, parse_mode="HTML")
