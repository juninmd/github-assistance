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
        self._info_cache: dict[str, GhRepository | None] = {}

    @staticmethod
    def _owner_from_repository(repository: str) -> str:
        if not isinstance(repository, str) or "/" not in repository:
            return ""
        return repository.split("/", 1)[0].strip().lower()

    def _is_target_owner_repo(self, repository: str) -> bool:
        return self._owner_from_repository(repository) == self.target_owner.strip().lower()

    def get_allowed_repositories(self, enforce_allowlist: bool) -> list[str]:
        all_repos = {
            repo for repo in self.allowlist.list_repositories()
            if self._is_target_owner_repo(repo)
        }

        try:
            user_repos = self.github.get_user_repos(limit=None)
            for repo in user_repos:
                if repo.owner.login.strip().lower() != self.target_owner.strip().lower():
                    continue
                if not enforce_allowlist or self.allowlist.is_allowed(repo.full_name):
                    all_repos.add(repo.full_name)
        except Exception as e:
            self.log(f"Error fetching user repositories: {e}", "WARNING")

        return sorted(list(all_repos))

    def can_work_on(self, repository: str, enforce_allowlist: bool) -> bool:
        if not self._is_target_owner_repo(repository):
            return False
        return not enforce_allowlist or self.allowlist.is_allowed(repository)

    def get_info(self, repository: str) -> GhRepository | None:
        if repository in self._info_cache:
            return self._info_cache[repository]
        if not self._is_target_owner_repo(repository):
            self.log(f"Repository denied by owner scope: {repository}", "WARNING")
            self._info_cache[repository] = None
            return None
        try:
            repo = self.github.get_repo(repository)
            self._info_cache[repository] = repo
            return repo
        except Exception as e:
            self.log(f"Error getting repository {repository}: {e}", "ERROR")
            self._info_cache[repository] = None
            return None
