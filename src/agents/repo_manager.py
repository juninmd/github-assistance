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
        from datetime import UTC, datetime

        all_repos = {
            repo for repo in self.allowlist.list_repositories() if self._is_target_owner_repo(repo)
        }

        repo_pushed_dates = {}
        try:
            user_repos = self.github.get_user_repos(limit=None)
            for repo in user_repos:
                if repo.owner.login.strip().lower() != self.target_owner.strip().lower():
                    continue
                if not enforce_allowlist or self.allowlist.is_allowed(repo.full_name):
                    all_repos.add(repo.full_name)
                    pushed = getattr(repo, "pushed_at", None)
                    if isinstance(pushed, datetime):
                        repo_pushed_dates[repo.full_name.lower().strip()] = pushed
        except Exception as e:
            self.log(f"Error fetching user repositories: {e}", "WARNING")

        epoch = datetime.fromtimestamp(0, UTC)

        def get_sort_key(repo_name: str) -> tuple[datetime, str]:
            name_key = repo_name.lower().strip()
            pushed_at = repo_pushed_dates.get(name_key)
            if pushed_at is None:
                try:
                    info = self.get_info(repo_name)
                    if info:
                        pushed = getattr(info, "pushed_at", None)
                        if isinstance(pushed, datetime):
                            pushed_at = pushed
                except Exception:
                    pass
            if pushed_at is None:
                pushed_at = epoch
            if pushed_at.tzinfo is not None:
                pushed_at = pushed_at.replace(tzinfo=None)
            return (pushed_at, name_key)

        return sorted(list(all_repos), key=get_sort_key)

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
