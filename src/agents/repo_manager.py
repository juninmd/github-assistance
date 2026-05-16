"""
Repository Manager - Handles discovery and allowlist checks.
"""
from collections.abc import Callable

from github.Repository import Repository as GhRepository

from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient


class RepositoryManager:
    """Manages repository discovery and access control."""

    def __init__(
        self,
        github_client: GithubClient,
        allowlist: RepositoryAllowlist,
        target_owner: str,
        log_func: Callable[[str, str], None],
    ):
        self.github = github_client
        self.allowlist = allowlist
        self.target_owner = target_owner
        self.log = log_func

    def get_allowed_repositories(self, enforce_allowlist: bool) -> list[str]:
        if enforce_allowlist:
            return self.allowlist.list_repositories()

        repos = self.github.get_user_repos(limit=None)
        return [r.full_name for r in repos if r.owner.login == self.target_owner]

    def can_work_on(self, repository: str, enforce_allowlist: bool) -> bool:
        if not enforce_allowlist:
            return True
        return self.allowlist.is_allowed(repository)

    def get_info(self, repository: str) -> GhRepository | None:
        try:
            return self.github.get_repo(repository)
        except Exception as e:
            self.log(f"Error getting repository {repository}: {e}", "ERROR")
            return None
