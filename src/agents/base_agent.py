"""
Base Agent class for all development agents.
"""
from abc import ABC, abstractmethod
from typing import Any

from src.agents import utils
from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier


class BaseAgent(ABC):
    """
    Abstract base class for all development agents.
    Each agent has a specific persona and mission.
    """

    def __init__(
        self,
        jules_client: JulesClient,
        github_client: GithubClient,
        allowlist: RepositoryAllowlist,
        telegram: TelegramNotifier | None = None,
        name: str = "BaseAgent",
        enforce_repository_allowlist: bool = True,
        target_owner: str = "juninmd",
        **kwargs,
    ):
        self.jules_client = jules_client
        self.github_client = github_client
        self.allowlist = allowlist
        self.telegram = telegram or TelegramNotifier()
        self.name = name
        self.enforce_repository_allowlist = enforce_repository_allowlist
        self.target_owner = target_owner
        self._instructions_cache: str | None = None

    @property
    @abstractmethod
    def persona(self) -> str:
        pass  # pragma: no cover

    @property
    @abstractmethod
    def mission(self) -> str:
        pass  # pragma: no cover

    def load_instructions(self) -> str:
        """Load agent instructions from markdown file."""
        if self._instructions_cache:
            return self._instructions_cache

        self._instructions_cache = utils.load_instructions(self.name, self.log)
        return self._instructions_cache

    def load_jules_instructions(
        self,
        template_name: str = "jules-instructions.md",
        variables: dict[str, Any] | None = None,
    ) -> str:
        """Load Jules task instructions from markdown template and replace variables."""
        return utils.load_jules_instructions(self.name, template_name, variables, self.log)

    def get_instructions_section(self, section_header: str) -> str:
        """Extract a specific section from instructions markdown."""
        return utils.get_instructions_section(self.load_instructions(), section_header)

    def get_allowed_repositories(self) -> list[str]:
        return self.allowlist.list_repositories()

    def uses_repository_allowlist(self) -> bool:
        return self.enforce_repository_allowlist

    def can_work_on_repository(self, repository: str) -> bool:
        if not self.enforce_repository_allowlist:
            return True
        return self.allowlist.is_allowed(repository)

    @abstractmethod
    def run(self) -> dict[str, Any]:
        pass  # pragma: no cover

    def check_rate_limit(self) -> int:
        """Check GitHub API rate limit and log a warning if running low.

        Returns the number of remaining requests.
        """
        return utils.check_github_rate_limit(self.github_client, self.log)

    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}] [{level}] {message}")

    def has_recent_jules_session(self, repository: str, task_keyword: str = "", hours: int = 24) -> bool:
        """Check if a Jules session was already created recently for this repo/task."""
        return utils.has_recent_jules_session(
            self.jules_client, repository, task_keyword, hours, self.log
        )

    def create_jules_session(
        self,
        repository: str,
        instructions: str,
        title: str,
        wait_for_completion: bool = False,
        base_branch: str = "main",
    ) -> dict[str, Any]:
        """Create a Jules session with agent's persona context."""
        if not self.can_work_on_repository(repository):
            raise ValueError(f"Repository {repository} is not in the allowlist")

        self.log(f"Creating Jules session for {repository}: {title}")

        prompt = f"""# Agent Context
Persona: {self.persona}
Mission: {self.mission}

# Task Instructions
{instructions}
"""
        result = self.jules_client.create_pull_request_session(
            repository=repository, prompt=prompt, title=title, base_branch=base_branch,
        )
        session_id = result.get("id")
        self.log(f"Created session {session_id}")

        if wait_for_completion and session_id:
            self.log(f"Waiting for session {session_id} to complete...")
            result = self.jules_client.wait_for_session(session_id)
            self.log(f"Session {session_id} completed")

        return result

    def get_repository_info(self, repository: str) -> Any | None:
        try:
            return self.github_client.get_repo(repository)
        except Exception as e:
            self.log(f"Error getting repository {repository}: {e}", "ERROR")
            return None
