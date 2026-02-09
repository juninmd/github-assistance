import os
import requests
import re
from github import Github, GithubException

class GithubClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.g = Github(self.token)
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    def _escape_markdown(self, text):
        """
        Escape special characters for Telegram MarkdownV2.
        For regular Markdown mode, we need to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
        """
        if not text:
            return text
        # Escape special markdown characters
        special_chars = ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def search_prs(self, query):
        """
        Searches for PRs using GitHub search syntax.
        """
        return self.g.search_issues(query)

    def get_pr_from_issue(self, issue):
        """
        Converts a search result Issue to a PullRequest object.
        """
        return issue.as_pull_request()

    def merge_pr(self, pr):
        try:
            pr.merge()
            return True, "Merged successfully"
        except GithubException as e:
            return False, str(e)

    def comment_on_pr(self, pr, body):
        pr.create_issue_comment(body)

    def get_issue_comments(self, pr):
        """
        Gets the list of issue comments for the PR.
        """
        return pr.get_issue_comments()

    def commit_file(self, pr, file_path, content, message):
        """
        Updates a file in the PR branch.
        """
        try:
            repo = pr.base.repo
            # Get contents from the specific ref (branch) of the PR to get the SHA
            contents = repo.get_contents(file_path, ref=pr.head.sha)
            repo.update_file(contents.path, message, content, contents.sha, branch=pr.head.ref)
            return True
        except GithubException as e:
            print(f"Error committing file: {e}")
            return False

    def send_telegram_msg(self, text, parse_mode="MarkdownV2", reply_markup=None):
        """
        Sends a generic message to Telegram.

        Args:
            text: Message text
            parse_mode: Parse mode (MarkdownV2, Markdown, or HTML)
            reply_markup: Optional inline keyboard or reply markup
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram credentials missing. Skipping notification.")
            return

        # Telegram has a 4096 character limit for messages
        MAX_LENGTH = 4096
        if len(text) > MAX_LENGTH:
            truncate_msg = "\n\n\\.\\.\\. \\(mensagem truncada\\)"
            # Ensure we don't cut in the middle of an escape sequence
            # If the cut point is a backslash, remove it
            cut_point = MAX_LENGTH - len(truncate_msg)
            truncated_text = text[:cut_point]
            if truncated_text.endswith('\\'):
                truncated_text = truncated_text[:-1]
            
            text = truncated_text + truncate_msg
            print(f"Warning: Telegram message truncated to {MAX_LENGTH} characters")

        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        # Log payload for debugging (masking the chat_id for safety if needed, but here we print full)
        import json
        print(f"DEBUG: Sending Telegram message payload:\n{json.dumps(payload, indent=2)}")

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    def send_telegram_notification(self, pr):
        """
        Sends a notification to Telegram about a merged PR with inline button.
        """
        title = self._escape_markdown(pr.title)
        user = self._escape_markdown(pr.user.login)
        url = pr.html_url
        repo = self._escape_markdown(pr.base.repo.full_name)
        body = self._escape_markdown(pr.body or "No description provided.")

        # Truncate body if too long
        if len(body) > 300:
            body = body[:297] + "\\.\\.\\."

        text = (
            f"🚀 *PR Merged\\!*\n\n"
            f"*Title:* {title}\n"
            f"*Repository:* {repo}\n"
            f"*Author:* {user}\n\n"
            f"*Description:*\n{body}"
        )

        # Add inline button to view PR
        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "🔗 Ver PR", "url": url}
            ]]
        }

        if self.send_telegram_msg(text, parse_mode="MarkdownV2", reply_markup=inline_keyboard):
            print(f"Telegram notification sent for PR #{pr.number}")
