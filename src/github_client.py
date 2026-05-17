import os
import re
from collections import defaultdict

from github import Github, GithubException
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.PullRequest import PullRequest
from github.Repository import Repository
from urllib3.util.retry import Retry


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

    def get_user_repos(self, sort: str = "updated", direction: str = "desc", limit: int | None = 10) -> list[Repository]:
        user = self.g.get_user()
        repos = user.get_repos(sort=sort, direction=direction)
        if limit is None:
            return list(repos)
        return list(repos[:limit])

    def merge_pr(self, pr: PullRequest, merge_method: str = "squash") -> tuple[bool, str]:
        last_error: GithubException | None = None
        try:
            pr.merge(merge_method=merge_method)
            return True, "Merged successfully"
        except GithubException as e:
            last_error = e

        if not self._is_base_branch_modified_error(last_error):
            return False, str(last_error)

        try:
            refreshed_pr = pr.base.repo.get_pull(pr.number)
            refreshed_pr.merge(merge_method=merge_method)
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
            repo.update_file(contents.path, message, content, contents.sha, branch=pr.head.ref)
            return True
        except GithubException as e:
            print(f"Error committing file: {e}")
            return False

    @staticmethod
    def _normalize_login(login: str | None) -> str:
        normalized = (login or "").strip().lower()
        if normalized.endswith("[bot]"):
            normalized = normalized[:-5]
        return normalized

    def accept_review_suggestions(self, pr: PullRequest, bot_usernames: list[str]) -> tuple[bool, str, int]:
        try:
            suggestions_applied = 0
            normalized_bots = {
                self._normalize_login(username)
                for username in bot_usernames
                if isinstance(username, str) and username.strip()
            }

            try:
                review_comments = list(pr.get_review_comments())
            except GithubException as e:
                return False, f"Failed to fetch review comments: {e.status} {e.data}", 0

            file_suggestions: dict[str, list[dict]] = defaultdict(list)

            for comment in review_comments:
                comment_login = self._normalize_login(getattr(comment.user, "login", ""))
                if comment_login not in normalized_bots:
                    continue

                suggestion_pattern = r'```suggestion[^\r\n]*\r?\n(.*?)\r?\n```'
                suggestions = re.findall(suggestion_pattern, comment.body or "", re.DOTALL)

                if not suggestions:
                    continue

                for suggestion in suggestions:
                    file_path = comment.path
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
                        start_idx = line - 1
                        end_idx = line

                    file_suggestions[file_path].append({
                        "start_idx": start_idx,
                        "end_idx": end_idx,
                        "suggestion": suggestion,
                        "author": comment.user.login,
                    })

            if not file_suggestions:
                return True, "No suggestions found to apply", 0

            repo = pr.head.repo
            for file_path, suggestions in file_suggestions.items():
                try:
                    file_content = repo.get_contents(file_path, ref=pr.head.ref)
                    current_content = file_content.decoded_content.decode('utf-8')
                    lines = current_content.split('\n')

                    suggestions.sort(key=lambda x: x["start_idx"], reverse=True)

                    authors = set()
                    local_applied = 0
                    for sugg in suggestions:
                        suggestion_lines = sugg["suggestion"].split('\n')
                        lines = lines[:sugg["start_idx"]] + suggestion_lines + lines[sugg["end_idx"]:]
                        authors.add(sugg["author"])
                        local_applied += 1

                    new_content = '\n'.join(lines)
                    author_list = ", ".join(authors)
                    co_authors = "\n".join(
                        f"Co-authored-by: {a} <{a}@users.noreply.github.com>" for a in authors
                    )
                    commit_message = f"Apply suggestion from {author_list}\n\n{co_authors}"

                    repo.update_file(
                        file_path, commit_message, new_content,
                        file_content.sha, branch=pr.head.ref,
                    )
                    suggestions_applied += local_applied
                    print(f"Applied {len(suggestions)} suggestion(s) to {file_path}")

                except Exception as e:
                    print(f"Error applying suggestion(s) to {file_path}: {e}")
                    continue

            if suggestions_applied > 0:
                return True, f"Applied {suggestions_applied} suggestion(s)", suggestions_applied
            return True, "No suggestions found to apply", 0

        except Exception as e:
            return False, f"Error processing review suggestions: {e}", 0
