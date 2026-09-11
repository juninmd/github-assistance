import os

import requests
from github import Github, GithubException
from github.GithubObject import NotSet
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.PullRequest import PullRequest
from github.Repository import Repository
from urllib3.util.retry import Retry

from src import review_suggestions

_UPDATE_BRANCH_TIMEOUT = 30


class GithubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.g = Github(
            self.token,
            timeout=300,
            retry=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503]),
        )

    def search_prs(self, query: str) -> list[Issue]:
        return list(self.g.search_issues(query))

    def get_pr_from_issue(self, issue: Issue) -> PullRequest:
        return issue.as_pull_request()

    def get_repo(self, repo_name: str) -> Repository:
        return self.g.get_repo(repo_name)

    def get_user_repos(
        self, sort: str = "updated", direction: str = "desc", limit: int | None = 10
    ) -> list[Repository]:
        from itertools import islice

        repos = self.g.get_user().get_repos(sort=sort, direction=direction)
        if limit is None:
            return list(repos)
        return list(islice(repos, limit))

    def update_pr_branch(
        self, pr: PullRequest, expected_head_sha: str | None = None
    ) -> tuple[bool, str, str]:
        """Update the PR branch against its base. Returns (ok, msg, head_sha)."""
        url = f"https://api.github.com/repos/{pr.base.repo.full_name}/pulls/{pr.number}/update-branch"
        body = {"expected_head_sha": expected_head_sha} if expected_head_sha else None
        try:
            resp = requests.post(
                url,
                json=body,
                headers={
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=_UPDATE_BRANCH_TIMEOUT,
            )
        except requests.RequestException as e:
            return False, f"update-branch request failed: {e}", ""
        if resp.status_code not in (200, 202):
            return False, f"update-branch failed ({resp.status_code}): {resp.text[:200]}", ""
        try:
            pr = pr.base.repo.get_pull(pr.number)
            return True, "Branch updated", pr.head.sha
        except GithubException:
            return True, "Branch updated (head SHA unknown)", ""

    def merge_pr(
        self,
        pr: PullRequest,
        merge_method: str = "squash",
        expected_sha: str | None = None,
    ) -> tuple[bool, str]:
        """Merge only if the head SHA still matches the SHA validated earlier."""
        try:
            current = pr.base.repo.get_pull(pr.number)
        except GithubException as e:
            return False, f"could not re-fetch PR before merge: {e}"
        if expected_sha and current.head.sha != expected_sha:
            return (
                False,
                f"HEAD changed since validation (expected {expected_sha[:8]}, "
                f"got {current.head.sha[:8]}); re-validate before merging",
            )
        # GitHub rejects the merge (409) if the head moved after our SHA check.
        sha_lock = expected_sha or NotSet
        last_error: GithubException | None = None
        try:
            current.merge(merge_method=merge_method, sha=sha_lock)
            return True, "Merged successfully"
        except GithubException as e:
            last_error = e

        if not self._is_base_branch_modified_error(last_error):
            return False, str(last_error)

        try:
            refreshed = current.base.repo.get_pull(current.number)
            if expected_sha and refreshed.head.sha != expected_sha:
                return False, "HEAD changed after base update; re-validate before merging"
            refreshed.merge(merge_method=merge_method, sha=sha_lock)
            return True, "Merged successfully after refreshing PR base"
        except GithubException as e:
            return False, str(e)

    @staticmethod
    def _is_base_branch_modified_error(error: GithubException | None) -> bool:
        if error is None:
            return False
        details = str(error).lower()
        data = getattr(error, "data", None)
        if isinstance(data, dict):
            details = f"{details} {data.get('message', '')}".lower()
        return getattr(error, "status", None) == 405 and "base branch was modified" in details

    def comment_on_pr(self, pr: PullRequest, body: str) -> None:
        pr.create_issue_comment(body)

    def add_label_to_pr(self, pr: PullRequest, label: str) -> tuple[bool, str]:
        try:
            pr.as_issue().add_to_labels(label)
            return True, f"Label '{label}' added"
        except GithubException as e:
            return False, str(e)

    def pr_has_non_bot_commits(self, pr: PullRequest, bot_login: str = "dependabot[bot]") -> bool:
        try:
            for commit in pr.get_commits():
                author = commit.author.login if commit.author else None
                if author and author.lower() not in (bot_login.lower(), self._normalize_login(bot_login)):
                    return True
            return False
        except GithubException:
            return False

    def add_assignee_to_pr(self, pr: PullRequest, login: str) -> tuple[bool, str]:
        try:
            pr.as_issue().add_to_assignees(login)
            return True, f"Assigned '{login}'"
        except GithubException as e:
            return False, str(e)

    def get_issue_comments(self, pr: PullRequest) -> list[IssueComment]:
        return list(pr.get_issue_comments())

    def close_pr(self, pr: PullRequest) -> tuple[bool, str]:
        try:
            pr.edit(state="closed")
            return True, "PR closed successfully"
        except GithubException as e:
            return False, str(e)

    def commit_file(self, pr: PullRequest, file_path: str, content: str, message: str) -> bool:
        try:
            repo = pr.base.repo
            contents = repo.get_contents(file_path, ref=pr.head.sha)
            if isinstance(contents, list):
                return False
            repo.update_file(contents.path, message, content, contents.sha, branch=pr.head.ref)
            return True
        except GithubException as e:
            print(f"Error committing file: {e}")
            return False

    @staticmethod
    def _normalize_login(login: str | None) -> str:
        return review_suggestions.normalize_login(login)

    def accept_review_suggestions(self, pr: PullRequest, bot_usernames: list[str]) -> tuple[bool, str, int]:
        return review_suggestions.accept_review_suggestions(self, pr, bot_usernames)
