"""
Base Agent class for all development agents.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

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
    ):
        self.jules_client = jules_client
        self.github_client = github_client
        self.allowlist = allowlist
        self.telegram = telegram or TelegramNotifier()
        self.name = name
        self.enforce_repository_allowlist = enforce_repository_allowlist
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

        agent_dir = Path(__file__).parent / self.name
        instructions_file = agent_dir / 'instructions.md'

        if not instructions_file.exists():
            self.log(f"Instructions file not found: {instructions_file}", "WARNING")
            return ""

        try:
            with open(instructions_file, encoding='utf-8') as f:
                self._instructions_cache = f.read()
            return self._instructions_cache
        except Exception as e:
            self.log(f"Error loading instructions: {e}", "ERROR")
            return ""

    def load_jules_instructions(
        self,
        template_name: str = "jules-instructions.md",
        variables: dict[str, Any] | None = None,
    ) -> str:
        """Load Jules task instructions from markdown template and replace variables."""
        agent_dir = Path(__file__).parent / self.name
        template_file = agent_dir / template_name

        if not template_file.exists():
            self.log(f"Jules instructions template not found: {template_file}", "ERROR")
            return ""

        try:
            with open(template_file, encoding='utf-8') as f:
                template = f.read()

            if variables:
                for key, value in variables.items():
                    placeholder = f"{{{{{key}}}}}"
                    template = template.replace(placeholder, str(value))

            return template

        except Exception as e:
            self.log(f"Error loading Jules instructions: {e}", "ERROR")
            return ""

    def get_instructions_section(self, section_header: str) -> str:
        """Extract a specific section from instructions markdown."""
        instructions = self.load_instructions()
        if not instructions:
            return ""

        lines = instructions.split('\n')
        section_lines = []
        in_section = False
        header_level = 0

        for line in lines:
            if line.strip().startswith('#') and section_header.lower() in line.lower():
                in_section = True
                header_level = len(line.split()[0])
                continue

            if in_section:
                if line.strip().startswith('#'):
                    current_level = len(line.split()[0])
                    if current_level <= header_level:
                        break
                section_lines.append(line)

        return '\n'.join(section_lines).strip()

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
        try:
            rate_limit = self.github_client.g.get_rate_limit()
            remaining = rate_limit.rate.remaining
            limit = rate_limit.rate.limit
            pct = (remaining / limit * 100) if limit else 0

            if pct < 10:
                self.log(f"⚠️ GitHub API rate limit critical: {remaining}/{limit} ({pct:.0f}%)", "WARNING")
            elif pct < 25:
                self.log(f"GitHub API rate limit low: {remaining}/{limit} ({pct:.0f}%)", "WARNING")

            return remaining
        except Exception as e:
            self.log(f"Could not check rate limit: {e}", "WARNING")
            return -1

    def log(self, message: str, level: str = "INFO"):
        print(f"[{self.name}] [{level}] {message}")

    def has_recent_jules_session(self, repository: str, task_keyword: str = "", hours: int = 24) -> bool:
        """Check if a Jules session was already created recently for this repo/task.

        Prevents duplicate sessions for the same repository within the time window.
        """
        try:
            from datetime import UTC, datetime, timedelta
            sessions = self.jules_client.list_sessions(page_size=100)
            cutoff = datetime.now(UTC) - timedelta(hours=hours)

            for session in sessions:
                created_at = session.get("createTime") or session.get("createdAt")
                if not created_at:
                    continue
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue

                title = (session.get("title") or "").lower()
                repo_match = repository.lower() in title
                task_match = not task_keyword or task_keyword.lower() in title

                if repo_match and task_match:
                    self.log(f"Skipping duplicate: recent session found for {repository} ({task_keyword})")
                    return True
            return False
        except Exception as e:
            self.log(f"Could not check recent sessions: {e}", "WARNING")
            return False

    def create_jules_session(
        self,
        repository: str,
        instructions: str,
        title: str,
        wait_for_completion: bool = False,
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
            repository=repository, prompt=prompt, title=title,
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
