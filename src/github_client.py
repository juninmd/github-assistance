import os
import re

import requests
from github import Github, GithubException
from urllib3.util.retry import Retry


class GithubClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.g = Github(
            self.token,
            timeout=30,
            retry=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503]),
        )
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

    def get_repo(self, repo_name):
        """
        Gets a repository object by name.
        """
        return self.g.get_repo(repo_name)

    def merge_pr(self, pr):
        try:
            pr.merge()
            return True, "Merged successfully"
        except GithubException as e:
            return False, str(e)

    def comment_on_pr(self, pr, body):
        pr.create_issue_comment(body)

    def add_label_to_pr(self, pr, label):
        """Add a label to the PR issue."""
        try:
            pr.as_issue().add_to_labels(label)
            return True, f"Label '{label}' added"
        except GithubException as e:
            return False, str(e)

    def get_issue_comments(self, pr):
        """
        Gets the list of issue comments for the PR.
        """
        return pr.get_issue_comments()

    def close_pr(self, pr):
        """Close a pull request."""
        try:
            pr.edit(state="closed")
            return True, "PR closed successfully"
        except GithubException as e:
            return False, str(e)

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
            f"🚀 *PR Mergeado\\!*\n\n"
            f"📦 *Repositorio:* `{repo}`\n"
            f"📌 *Titulo:* {title}\n"
            f"👤 *Autor:* {user}\n\n"
            f"*Descrição:*\n{body}"
        )

        # Add inline button to view PR
        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "🔗 Ver PR", "url": url}
            ]]
        }

        if self.send_telegram_msg(text, parse_mode="MarkdownV2", reply_markup=inline_keyboard):
            print(f"Telegram notification sent for PR #{pr.number}")

    @staticmethod
    def _normalize_login(login):
        """Normalize GitHub login for matching bot usernames."""
        normalized = (login or "").strip().lower()
        if normalized.endswith("[bot]"):
            normalized = normalized[:-5]
        return normalized

    def accept_review_suggestions(self, pr, bot_usernames):
        """
        Accept review suggestions from specified bot users.

        Args:
            pr: GitHub PR object
            bot_usernames: List of bot usernames to accept suggestions from

        Returns:
            Tuple of (success: bool, message: str, suggestions_applied: int)
        """
        try:
            suggestions_applied = 0
            normalized_bots = {
                self._normalize_login(username)
                for username in bot_usernames
                if isinstance(username, str) and username.strip()
            }

            # Get all review comments
            try:
                review_comments = list(pr.get_review_comments())
            except GithubException as e:
                return False, f"Failed to fetch review comments: {e.status} {e.data}", 0

            # Group suggestions by file path
            file_suggestions = {}

            for comment in review_comments:
                # Check if comment is from one of the bot users
                comment_login = self._normalize_login(getattr(comment.user, "login", ""))
                if comment_login not in normalized_bots:
                    continue

                # Extract suggestions from comment body
                suggestion_pattern = r'```suggestion[^\r\n]*\r?\n(.*?)\r?\n```'
                suggestions = re.findall(suggestion_pattern, comment.body or "", re.DOTALL)

                if not suggestions:
                    continue

                # For each suggestion found
                for suggestion in suggestions:
                    file_path = comment.path

                    # Calculate line numbers
                    line = getattr(comment, "line", None)
                    start_line = getattr(comment, "start_line", None)

                    if not isinstance(line, int) or line <= 0:
                        print(f"Skipping suggestion from {comment.user.login}: invalid line reference")
                        continue

                    if isinstance(start_line, int) and start_line > 0:
                        start = min(start_line, line)
                        end = max(start_line, line)
                        start_idx = start - 1
                        end_idx = end
                    else:
                        # Single line suggestion
                        start_idx = line - 1
                        end_idx = line

                    if file_path not in file_suggestions:
                        file_suggestions[file_path] = []

                    file_suggestions[file_path].append({
                        "start_idx": start_idx,
                        "end_idx": end_idx,
                        "suggestion": suggestion,
                        "author": comment.user.login
                    })

            if not file_suggestions:
                return True, "No suggestions found to apply", 0

            # Process suggestions file by file
            repo = pr.head.repo
            for file_path, suggestions in file_suggestions.items():
                try:
                    # Get current file content from PR branch
                    file_content = repo.get_contents(file_path, ref=pr.head.ref)
                    current_content = file_content.decoded_content.decode('utf-8')
                    lines = current_content.split('\n')

                    # Sort suggestions by start_idx descending to apply bottom-up
                    # This prevents line shifts from affecting subsequent suggestions
                    suggestions.sort(key=lambda x: x["start_idx"], reverse=True)

                    authors = set()
                    local_suggestions_applied = 0
                    for sugg in suggestions:
                        # Split suggestion into lines if it's multiline
                        suggestion_lines = sugg["suggestion"].split('\n')
                        lines = lines[:sugg["start_idx"]] + suggestion_lines + lines[sugg["end_idx"]:]
                        authors.add(sugg["author"])
                        local_suggestions_applied += 1

                    new_content = '\n'.join(lines)

                    # Create commit message
                    author_list = ", ".join(authors)
                    co_authors = "\n".join([f"Co-authored-by: {author} <{author}@users.noreply.github.com>" for author in authors])
                    commit_message = f"Apply suggestion from {author_list}\n\n{co_authors}"

                    repo.update_file(
                        file_path,
                        commit_message,
                        new_content,
                        file_content.sha,
                        branch=pr.head.ref
                    )

                    suggestions_applied += local_suggestions_applied
                    print(f"Applied {len(suggestions)} suggestion(s) to {file_path}")

                except Exception as e:
                    print(f"Error applying suggestion(s) to {file_path}: {e}")
                    continue

            if suggestions_applied > 0:
                return True, f"Applied {suggestions_applied} suggestion(s)", suggestions_applied
            else:
                return True, "No suggestions found to apply", 0

        except Exception as e:
            return False, f"Error processing review suggestions: {e}", 0
