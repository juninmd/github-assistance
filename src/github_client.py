import os
import re

from github import Github, GithubException
from urllib3.util.retry import Retry


class GithubClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.g = Github(
            self.token,
            timeout=300,
            retry=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503]),
        )

    def search_prs(self, query):
        """Searches for PRs using GitHub search syntax."""
        return self.g.search_issues(query)

    def get_pr_from_issue(self, issue):
        """Converts a search result Issue to a PullRequest object."""
        return issue.as_pull_request()

    def get_repo(self, repo_name):
        """Gets a repository object by name."""
        return self.g.get_repo(repo_name)

    def get_user_repos(self, sort="updated", direction="desc", limit=10):
        """Fetches the user's repositories, sorted by the specified criteria."""
        user = self.g.get_user()
        repos = user.get_repos(sort=sort, direction=direction)
        if limit is None:
            return list(repos)
        return [repo for repo in repos[:limit]]

    def merge_pr(self, pr, merge_method="squash"):
        try:
            pr.merge(merge_method=merge_method)
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
        """Gets the list of issue comments for the PR."""
        return pr.get_issue_comments()

    def close_pr(self, pr):
        """Close a pull request."""
        try:
            pr.edit(state="closed")
            return True, "PR closed successfully"
        except GithubException as e:
            return False, str(e)

    def commit_file(self, pr, file_path, content, message):
        """Updates a file in the PR branch."""
        try:
            repo = pr.base.repo
            contents = repo.get_contents(file_path, ref=pr.head.sha)
            repo.update_file(contents.path, message, content, contents.sha, branch=pr.head.ref)
            return True
        except GithubException as e:
            print(f"Error committing file: {e}")
            return False

    @staticmethod
    def _normalize_login(login):
        """Normalize GitHub login for matching bot usernames."""
        normalized = (login or "").strip().lower()
        if normalized.endswith("[bot]"):
            normalized = normalized[:-5]
        return normalized

    def _collect_review_suggestions(self, review_comments, normalized_bots):
        """Collect review suggestions from bot comments grouped by file."""
        file_suggestions = {}
        for comment in review_comments:
            comment_login = self._normalize_login(getattr(comment.user, "login", ""))
            if comment_login not in normalized_bots:
                continue

            suggestions = re.findall(r'```suggestion[^\r\n]*\r?\n(.*?)\r?\n```', comment.body or "", re.DOTALL)
            if not suggestions:
                continue

            for suggestion in suggestions:
                line = getattr(comment, "line", None)
                if not isinstance(line, int) or line <= 0:
                    print(f"Skipping suggestion from {comment.user.login}: invalid line reference")
                    continue

                start_line = getattr(comment, "start_line", None)
                if isinstance(start_line, int) and start_line > 0:
                    start_idx = min(start_line, line) - 1
                    end_idx = max(start_line, line)
                else:
                    start_idx = line - 1
                    end_idx = line

                file_suggestions.setdefault(comment.path, []).append({
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                    "suggestion": suggestion,
                    "author": comment.user.login,
                })
        return file_suggestions

    def _apply_file_suggestions(self, repo, branch_ref, file_path, suggestions):
        """Apply a batch of suggestions to a single file in the repo."""
        file_content = repo.get_contents(file_path, ref=branch_ref)
        lines = file_content.decoded_content.decode('utf-8').split('\n')

        suggestions.sort(key=lambda x: x["start_idx"], reverse=True)
        authors = set()
        for sugg in suggestions:
            suggestion_lines = sugg["suggestion"].split('\n')
            lines = lines[:sugg["start_idx"]] + suggestion_lines + lines[sugg["end_idx"]:]
            authors.add(sugg["author"])

        new_content = '\n'.join(lines)
        author_list = ", ".join(authors)
        co_authors = "\n".join(
            f"Co-authored-by: {a} <{a}@users.noreply.github.com>" for a in authors
        )
        repo.update_file(
            file_path,
            f"Apply suggestion from {author_list}\n\n{co_authors}",
            new_content,
            file_content.sha,
            branch=branch_ref,
        )
        print(f"Applied {len(suggestions)} suggestion(s) to {file_path}")
        return len(suggestions)

    def accept_review_suggestions(self, pr, bot_usernames):
        """Accept review suggestions from specified bot users."""
        try:
            normalized_bots = {
                self._normalize_login(username)
                for username in bot_usernames
                if isinstance(username, str) and username.strip()
            }

            try:
                review_comments = list(pr.get_review_comments())
            except GithubException as e:
                return False, f"Failed to fetch review comments: {e.status} {e.data}", 0

            file_suggestions = self._collect_review_suggestions(review_comments, normalized_bots)
            if not file_suggestions:
                return True, "No suggestions found to apply", 0

            repo = pr.head.repo
            suggestions_applied = 0
            for file_path, suggestions in file_suggestions.items():
                try:
                    suggestions_applied += self._apply_file_suggestions(repo, pr.head.ref, file_path, suggestions)
                except Exception as e:
                    print(f"Error applying suggestion(s) to {file_path}: {e}")

            if suggestions_applied > 0:
                return True, f"Applied {suggestions_applied} suggestion(s)", suggestions_applied
            return True, "No suggestions found to apply", 0

        except Exception as e:
            return False, f"Error processing review suggestions: {e}", 0
