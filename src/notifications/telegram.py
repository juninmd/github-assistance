"""Telegram notification service."""
import requests


class TelegramNotifier:
    """Sends messages and notifications via Telegram Bot API."""

    MAX_LENGTH = 4096

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None, prefix: str | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.prefix = prefix

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

        if self.prefix:
            text = f"*{self.escape(self.prefix)}*\n" + text

        text = self._truncate(text)
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        # Validate chat_id format early to catch obvious misconfiguration.
        # Telegram accepts numeric IDs and @username strings for channels.
        # We perform a simple check to catch common mistakes like empty strings
        # or whitespace-only values.
        if isinstance(self.chat_id, str) and not self.chat_id.strip():
            print("Failed to send Telegram message: chat_id is empty")
            return False

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
                timeout=10,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as http_err:
                # include response body for debugging
                body = response.text if hasattr(response, "text") else "<no body>"
                # If MarkdownV2 parse fails, retry as plain text to avoid losing the message
                if parse_mode and response.status_code == 400 and "can't parse entities" in body:
                    return self.send_message(text, parse_mode="", reply_markup=reply_markup)
                print(f"Failed to send Telegram message: {http_err}; response={body}")
                return False
            return True
        except Exception as e:
            # Generic failure (network error, timeout, etc.)
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
            f"🎊 *PULL REQUEST MERGEADO\\!* 🎊\n\n"
            f"🏢 *Repositorio:* `{repo}`\n"
            f"🆔 *PR:* `#{pr.number}`\n"
            f"📌 *Titulo:* *{title}*\n"
            f"👤 *Autor:* `{user}`\n\n"
            f"📖 *Descrição:*\n{body}"
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
