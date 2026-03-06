"""Telegram notification service."""
import requests


class TelegramNotifier:
    """Sends messages and notifications via Telegram Bot API."""

    MAX_LENGTH = 4096

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    @staticmethod
    def escape(text: str | None) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        if not text:
            return ""
        special_chars = [
            '\\', '_', '*', '[', ']', '(', ')', '~',
            '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!',
        ]
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def send_message(
        self,
        text: str,
        parse_mode: str = "MarkdownV2",
        reply_markup: dict | None = None,
    ) -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.enabled:
            print("Telegram credentials missing. Skipping notification.")
            return False

        text = self._truncate(text)
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    def send_pr_notification(self, pr) -> None:
        """Send a notification about a merged PR with inline button."""
        title = self.escape(pr.title)
        user = self.escape(pr.user.login)
        url = pr.html_url
        repo = self.escape(pr.base.repo.full_name)
        body = self.escape(pr.body or "No description provided.")

        if len(body) > 300:
            body = body[:297] + "\\.\\.\\.  "

        text = (
            f"🚀 *PR Mergeado\\!*\n\n"
            f"📦 *Repositorio:* `{repo}`\n"
            f"📌 *Titulo:* {title}\n"
            f"👤 *Autor:* {user}\n\n"
            f"*Descrição:*\n{body}"
        )
        inline_keyboard = {
            "inline_keyboard": [[{"text": "🔗 Ver PR", "url": url}]]
        }
        if self.send_message(text, parse_mode="MarkdownV2", reply_markup=inline_keyboard):
            print(f"Telegram notification sent for PR #{pr.number}")

    def _truncate(self, text: str) -> str:
        if len(text) <= self.MAX_LENGTH:
            return text
        truncate_msg = "\n\n\\.\\.\\. \\(mensagem truncada\\)"
        cut_point = self.MAX_LENGTH - len(truncate_msg)
        truncated = text[:cut_point]
        if truncated.endswith('\\'):
            truncated = truncated[:-1]
        print(f"Warning: Telegram message truncated to {self.MAX_LENGTH} characters")
        return truncated + truncate_msg
