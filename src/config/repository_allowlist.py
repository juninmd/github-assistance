from __future__ import annotations

import json
import os
from pathlib import Path

from src.utils.logger import get_logger

_logger = get_logger("allowlist")


class RepositoryAllowlist:
    DEFAULT_ALLOWLIST_PATH = "config/repositories.json"

    @staticmethod
    def _normalize_repository(repository: str | None) -> str:
        if not isinstance(repository, str):
            return ""
        return repository.lower().strip()

    def __init__(self, allowlist_path: str | None = None):
        self.allowlist_path = allowlist_path or os.getenv(
            "REPOSITORY_ALLOWLIST_PATH",
            self.DEFAULT_ALLOWLIST_PATH
        )
        self._repositories: set[str] = set()
        self.load()

    def load(self) -> None:
        try:
            allowlist_file = Path(self.allowlist_path)
            if allowlist_file.exists():
                with open(allowlist_file, encoding='utf-8') as f:
                    data = json.load(f)
                    repositories = data.get("repositories", [])
                    if not isinstance(repositories, list):
                        repositories = []

                    self._repositories = {
                        normalized
                        for normalized in (self._normalize_repository(repo) for repo in repositories)
                        if normalized
                    }
                    _logger.info(f"Loaded {len(self._repositories)} repositories from allowlist")
            else:
                _logger.warning(f"Allowlist file not found at {self.allowlist_path}. Using empty allowlist.")
                self._repositories = set()
        except Exception as e:
            _logger.error(f"Error loading allowlist: {e}")
            self._repositories = set()

    def save(self) -> None:
        try:
            allowlist_file = Path(self.allowlist_path)
            allowlist_file.parent.mkdir(parents=True, exist_ok=True)

            with open(allowlist_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "repositories": sorted(self._repositories),
                    "description": "List of repositories that agents are allowed to work on"
                }, f, indent=2, ensure_ascii=False)
            _logger.info(f"Saved {len(self._repositories)} repositories to allowlist")
        except Exception as e:
            _logger.error(f"Error saving allowlist: {e}")

    def is_allowed(self, repository: str) -> bool:
        normalized = self._normalize_repository(repository)
        if not normalized:
            return False
        return normalized in self._repositories

    def add_repository(self, repository: str) -> bool:
        normalized = self._normalize_repository(repository)
        if not normalized:
            return False
        if normalized not in self._repositories:
            self._repositories.add(normalized)
            self.save()
            return True
        return False

    def remove_repository(self, repository: str) -> bool:
        normalized = self._normalize_repository(repository)
        if not normalized:
            return False
        if normalized in self._repositories:
            self._repositories.remove(normalized)
            self.save()
            return True
        return False

    def list_repositories(self) -> list[str]:
        return sorted(self._repositories)

    def clear(self) -> None:
        self._repositories.clear()
        self.save()

    @classmethod
    def create_default_allowlist(cls, _owner: str = "juninmd") -> RepositoryAllowlist:
        allowlist = cls()
        return allowlist
