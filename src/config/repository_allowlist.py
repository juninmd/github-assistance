"""
Repository Allowlist Management.
Controls which repositories the agents are allowed to work on.
"""
import os
import json
from typing import List, Set
from pathlib import Path


class RepositoryAllowlist:
    """
    Manages the list of repositories that agents are allowed to access.
    """

    DEFAULT_ALLOWLIST_PATH = "config/repositories.json"

    def __init__(self, allowlist_path: str = None):
        """
        Initialize the repository allowlist.

        Args:
            allowlist_path: Path to the allowlist JSON file
        """
        self.allowlist_path = allowlist_path or os.getenv(
            "REPOSITORY_ALLOWLIST_PATH",
            self.DEFAULT_ALLOWLIST_PATH
        )
        self._repositories: Set[str] = set()
        self.load()

    def load(self):
        """Load the allowlist from file."""
        try:
            allowlist_file = Path(self.allowlist_path)
            if allowlist_file.exists():
                with open(allowlist_file, 'r') as f:
                    data = json.load(f)
                    self._repositories = set(data.get("repositories", []))
                    print(f"Loaded {len(self._repositories)} repositories from allowlist")
            else:
                print(f"Allowlist file not found at {self.allowlist_path}. Using empty allowlist.")
                self._repositories = set()
        except Exception as e:
            print(f"Error loading allowlist: {e}")
            self._repositories = set()

    def save(self):
        """Save the current allowlist to file."""
        try:
            allowlist_file = Path(self.allowlist_path)
            allowlist_file.parent.mkdir(parents=True, exist_ok=True)

            with open(allowlist_file, 'w') as f:
                json.dump({
                    "repositories": sorted(list(self._repositories)),
                    "description": "List of repositories that agents are allowed to work on"
                }, f, indent=2)
            print(f"Saved {len(self._repositories)} repositories to allowlist")
        except Exception as e:
            print(f"Error saving allowlist: {e}")

    def is_allowed(self, repository: str) -> bool:
        """
        Check if a repository is in the allowlist.

        Args:
            repository: Repository identifier (e.g., "owner/repo")

        Returns:
            True if the repository is allowed
        """
        # Normalize repository format
        normalized = repository.lower().strip()
        return normalized in self._repositories

    def add_repository(self, repository: str) -> bool:
        """
        Add a repository to the allowlist.

        Args:
            repository: Repository identifier (e.g., "owner/repo")

        Returns:
            True if added (was not already in list)
        """
        normalized = repository.lower().strip()
        if normalized not in self._repositories:
            self._repositories.add(normalized)
            self.save()
            return True
        return False

    def remove_repository(self, repository: str) -> bool:
        """
        Remove a repository from the allowlist.

        Args:
            repository: Repository identifier (e.g., "owner/repo")

        Returns:
            True if removed (was in list)
        """
        normalized = repository.lower().strip()
        if normalized in self._repositories:
            self._repositories.remove(normalized)
            self.save()
            return True
        return False

    def list_repositories(self) -> List[str]:
        """
        Get all allowed repositories.

        Returns:
            Sorted list of repository identifiers
        """
        return sorted(list(self._repositories))

    def clear(self):
        """Remove all repositories from the allowlist."""
        self._repositories.clear()
        self.save()

    @classmethod
    def create_default_allowlist(cls, owner: str = "juninmd") -> 'RepositoryAllowlist':
        """
        Create a default allowlist for a GitHub user.

        Args:
            owner: GitHub username

        Returns:
            New RepositoryAllowlist instance
        """
        allowlist = cls()
        # Could be populated with user's repositories via GitHub API
        return allowlist
