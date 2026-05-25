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

    def get_allowed_repositories(self, enforce_allowlist: bool) -> list[str]:
        allowlist_repos = set(self.allowlist.list_repositories())
        allowed_users = set(self.allowlist.list_users())
        
        # Add target_owner if not enforcing strict allowlist
        if not enforce_allowlist:
            allowed_users.add(self.target_owner)

        # Get all repositories for each allowed user
        all_repos = allowlist_repos.copy()
        
        # Searching by user is more efficient than listing all user repos and filtering
        # but since we already have get_user_repos, let's use it for the current user
        # and maybe just trust the allowlist for others?
        # Actually, let's just use the GitHub search to find all repos for allowed users
        # if we want to be thorough.
        
        # For the authenticated user, we can get all their repos (including orgs)
        try:
            user_repos = self.github.get_user_repos(limit=None)
            for repo in user_repos:
                if repo.owner.login.lower() in [u.lower() for u in allowed_users]:
                    all_repos.add(repo.full_name)
        except Exception as e:
            self.log(f"Error fetching user repositories: {e}", "WARNING")

        return sorted(list(all_repos))

    def can_work_on(self, repository: str, enforce_allowlist: bool) -> bool:
        if not enforce_allowlist:
            return True
        return self.allowlist.is_allowed(repository)

    def get_info(self, repository: str) -> GhRepository | None:
        if repository in self._info_cache:
            return self._info_cache[repository]
        try:
            repo = self.github.get_repo(repository)
            self._info_cache[repository] = repo
            return repo
        except Exception as e:
            self.log(f"Error getting repository {repository}: {e}", "ERROR")
            self._info_cache[repository] = None
            return None
