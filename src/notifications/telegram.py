"""Telegram notification service."""
import re

import requests

from src.utils.retry import with_retry


def _is_telegram_retryable(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        status = getattr(exc.response, "status_code", None)
        # 429 = rate limit; 5xx = server errors — retry those
        return status in {429, 500, 502, 503, 504}
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


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

    _ESCAPE_PATTERN = re.compile(r'([\\_\*\[\]\(\)~`>#\+\-=\|\{\}\.\!])')

    @staticmethod
    def escape(text: str | None) -> str:
        """Escape special characters for Telegram MarkdownV2 using single-pass regex."""
        if not text:
            return ""
        return TelegramNotifier._ESCAPE_PATTERN.sub(r'\\\1', text)

    @staticmethod
    def escape_html(text: str | None) -> str:
        """Escape special characters for Telegram HTML."""
        if not text:
            return ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.enabled:
            print("Telegram credentials missing. Skipping notification.")
            return False

        if isinstance(self.chat_id, str) and not self.chat_id.strip():
            print("Failed to send Telegram message: chat_id is empty")
            return False

        if self.prefix and f"<b>{self.prefix}</b>" not in text:
            text = f"<b>{self.prefix}</b>\n" + text

        # Split into parts if too long, preserving all content
        parts = self._split(text)
        success = True
        for i, part in enumerate(parts):
            markup = reply_markup if i == len(parts) - 1 else None
            success = self._post(part, parse_mode, markup) and success
        return success

    @with_retry(max_attempts=3, base_delay=2.0, retryable=_is_telegram_retryable)
    def _post(self, text: str, parse_mode: str, reply_markup: dict | None) -> bool:
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
                timeout=30,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as http_err:
                body = response.text if hasattr(response, "text") else "<no body>"
                if parse_mode and response.status_code == 400 and "can't parse entities" in body:
                    return self._post(text, parse_mode="", reply_markup=reply_markup)
                print(f"Failed to send Telegram message: {http_err}; response={body}")
                return False
            return True
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    def send_pr_notification(self, pr) -> None:
        """Send a notification about a merged PR with inline button."""
        title = pr.title
        user = pr.user.login
        url = pr.html_url
        repo = pr.base.repo.full_name
        body = pr.body or "Sem descrição."

        if len(body) > 300:
            body = body[:297] + "..."

        text = (
            f"🐙 <b>GITHUB ASSISTANCE</b>\n"
            f"──────────────────────\n"
            f"🎊 <b>PULL REQUEST MERGEADO!</b>\n\n"
            f"🏢 <b>Repositório:</b> <code>{repo}</code>\n"
            f"🆔 <b>PR:</b> <code>#{pr.number}</code>\n"
            f"📌 <b>Título:</b> <b>{title}</b>\n"
            f"👤 <b>Autor:</b> <code>{user}</code>\n\n"
            f"📖 <b>Descrição:</b>\n<i>{body}</i>\n"
            f"──────────────────────"
        )
        inline_keyboard = {
            "inline_keyboard": [[{"text": "🔗 Ver PR no GitHub", "url": url}]]
        }
        if self.send_message(text, parse_mode="HTML", reply_markup=inline_keyboard):
            print(f"Telegram notification sent for PR #{pr.number}")

    def _split(self, text: str) -> list[str]:
        """Split text into Telegram-safe chunks without breaking mid-word."""
        if len(text) <= self.MAX_LENGTH:
            return [text]

        parts: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= self.MAX_LENGTH:
                parts.append(remaining)
                break
            cut = remaining.rfind("\n", 0, self.MAX_LENGTH - 50)
            if cut == -1:
                cut = self.MAX_LENGTH - 50
            chunk = remaining[:cut].rstrip()
            total = (len(parts) + 1)
            parts.append(f"{chunk}\n\n<i>(parte {total})</i>")
            remaining = remaining[cut:].lstrip()

        # Annotate first part with total once we know it
        n = len(parts)
        if n > 1:
            parts = [p.replace(f"<i>(parte {i+1})</i>", f"<i>(parte {i+1}/{n})</i>") for i, p in enumerate(parts)]
            print(f"Warning: Telegram message split into {n} parts")
        return parts

    # Keep old _truncate for backwards compatibility
    def _truncate(self, text: str) -> str:
        return self._split(text)[0] if len(text) > self.MAX_LENGTH else text
