import os
import requests
from github import Github, GithubException

class GithubClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.g = Github(self.token)
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

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

    def send_telegram_msg(self, text, parse_mode="Markdown"):
        """
        Sends a generic message to Telegram.
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram credentials missing. Skipping notification.")
            return

        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }

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
        Sends a notification to Telegram about a merged PR.
        """
        title = pr.title
        user = pr.user.login
        url = pr.html_url
        body = pr.body or "No description provided."

        text = f"🚀 *PR Merged!*\n\n*Title:* {title}\n*Author:* {user}\n\n*Description:*\n{body}\n\n[View PR]({url})"
        
        if self.send_telegram_msg(text):
            print(f"Telegram notification sent for PR #{pr.number}")
