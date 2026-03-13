"""
Telegram summary helpers for the Secret Remover Agent.
"""
from typing import Any

from src.notifications.telegram import TelegramNotifier


def build_finding_message(
    repo_name: str,
    finding: dict[str, Any],
    original_line: str,
    modified_line: str,
    telegram: TelegramNotifier,
) -> str:
    """Build a detailed Telegram message for a single secret removal."""
    esc = telegram.escape
    file_path = finding.get("file", "unknown")
    line = finding.get("line", 0)
    reason = finding.get("_reason", "No reason provided")

    text = (
        f"🛡️ *Secret Removida do Histórico*\n\n"
        f"📦 Repositório: `{esc(repo_name)}`\n"
        f"📄 Arquivo: `{esc(file_path)}` \\(Linha {line}\\)\n"
        f"🤖 Motivo: _{esc(reason)}_\n\n"
        f"📝 *Conteúdo Original:*\n`{esc(original_line)}`\n\n"
        f"✨ *Após Remoção:*\n`{esc(modified_line)}`"
    )

    return text

def get_finding_buttons(file_url: str, commit_url: str):
    """Return inline keyboard buttons for the finding."""
    return [
        [
            {"text": "View File", "url": file_url},
            {"text": "View Commit", "url": commit_url},
        ]
    ]

def send_error_notification(
    telegram: TelegramNotifier,
    target_owner: str,
    error_message: str,
) -> None:
    """Send a plain error notification via Telegram."""
    esc = telegram.escape
    text = (
        "🔐 *Secret Remover — Erro*\n\n"
        f"❌ {esc(error_message)}\n\n"
        f"👤 Owner: `{esc(target_owner)}`"
    )
    telegram.send_message(text, parse_mode="MarkdownV2")
