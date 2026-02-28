"""
Base Agent class for all development agents.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient


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
        name: str = "BaseAgent"
    ):
        """
        Initialize base agent.

        Args:
            jules_client: Jules API client
            github_client: GitHub API client
            allowlist: Repository allowlist
            name: Agent name
        """
        self.jules_client = jules_client
        self.github_client = github_client
        self.allowlist = allowlist
        self.name = name
        self._instructions_cache: str | None = None

    @property
    @abstractmethod
    def persona(self) -> str:
        """
        Agent's persona description.
        This defines how the agent thinks and communicates.
        """
        pass  # pragma: no cover

    @property
    @abstractmethod
    def mission(self) -> str:
        """
        Agent's primary mission and responsibilities.
        """
        pass  # pragma: no cover

    def load_instructions(self) -> str:
        """
        Load agent instructions from markdown file.

        Returns:
            Full instructions content from markdown file
        """
        if self._instructions_cache:
            return self._instructions_cache

        # Determine instructions file path based on agent class
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

    def load_jules_instructions(self, template_name: str = "jules-instructions.md", variables: dict = None) -> str:
        """
        Load Jules task instructions from markdown template and replace variables.

        Args:
            template_name: Name of the Jules instructions file (default: jules-instructions.md)
            variables: Dictionary of variables to replace in template (e.g., {"repository": "owner/repo"})

        Returns:
            Instructions with variables replaced

        Example:
            instructions = self.load_jules_instructions(
                template_name="jules-instructions-security.md",
                variables={"repository": "juninmd/myproject", "issues": "- Issue 1\\n- Issue 2"}
            )
        """
        # Determine instructions file path based on agent class
        agent_dir = Path(__file__).parent / self.name
        template_file = agent_dir / template_name

        if not template_file.exists():
            self.log(f"Jules instructions template not found: {template_file}", "ERROR")
            return ""

        try:
            with open(template_file, encoding='utf-8') as f:
                template = f.read()

            # Replace variables in template
            if variables:
                for key, value in variables.items():
                    placeholder = f"{{{{{key}}}}}"  # {{variable}}
                    template = template.replace(placeholder, str(value))

            return template

        except Exception as e:
            self.log(f"Error loading Jules instructions: {e}", "ERROR")
            return ""

    def get_instructions_section(self, section_header: str) -> str:
        """
        Extract a specific section from instructions markdown.

        Args:
            section_header: The header to search for (e.g., "## Jules Task Instructions")

        Returns:
            Content of the section
        """
        instructions = self.load_instructions()
        if not instructions:
            return ""

        lines = instructions.split('\n')
        section_lines = []
        in_section = False
        header_level = 0

        for line in lines:
            # Check if we're starting the desired section
            if line.strip().startswith('#') and section_header.lower() in line.lower():
                in_section = True
                header_level = len(line.split()[0])  # Count # characters
                continue

            # If we're in the section
            if in_section:
                # Check if we've hit another header of same or higher level
                if line.strip().startswith('#'):
                    current_level = len(line.split()[0])
                    if current_level <= header_level:
                        break

                section_lines.append(line)

        return '\n'.join(section_lines).strip()

    def get_allowed_repositories(self) -> list[str]:
        """
        Get list of repositories this agent can work on.

        Returns:
            List of repository identifiers
        """
        return self.allowlist.list_repositories()

    def can_work_on_repository(self, repository: str) -> bool:
        """
        Check if agent can work on a repository.

        Args:
            repository: Repository identifier (e.g., "owner/repo")

        Returns:
            True if allowed
        """
        return self.allowlist.is_allowed(repository)

    @abstractmethod
    def run(self) -> dict[str, Any]:
        """
        Execute the agent's primary workflow.

        Returns:
            Execution summary with results and metrics
        """
        pass  # pragma: no cover

    def log(self, message: str, level: str = "INFO"):
        """
        Log a message with agent context.

        Args:
            message: Message to log
            level: Log level (INFO, WARNING, ERROR)
        """
        print(f"[{self.name}] [{level}] {message}")

    def create_jules_session(
        self,
        repository: str,
        instructions: str,
        title: str,
        wait_for_completion: bool = False
    ) -> dict[str, Any]:
        """
        Create a Jules session with agent's persona context.

        Uses the v1alpha sessions API with AUTO_CREATE_PR mode.

        Args:
            repository: Target repository (e.g., 'owner/repo')
            instructions: Task instructions
            title: Session title
            wait_for_completion: Whether to wait for session completion

        Returns:
            Session result with 'id' and 'name'
        """
        if not self.can_work_on_repository(repository):
            raise ValueError(f"Repository {repository} is not in the allowlist")

        self.log(f"Creating Jules session for {repository}: {title}")

        # Inject agent persona into the prompt
        prompt = f"""# Agent Context
Persona: {self.persona}
Mission: {self.mission}

# Task Instructions
{instructions}
"""

        result = self.jules_client.create_pull_request_session(
            repository=repository,
            prompt=prompt,
            title=title
        )

        session_id = result.get("id")
        self.log(f"Created session {session_id}")

        if wait_for_completion and session_id:
            self.log(f"Waiting for session {session_id} to complete...")
            result = self.jules_client.wait_for_session(session_id)
            self.log(f"Session {session_id} completed")

        return result

    def get_repository_info(self, repository: str) -> Any | None:
        """
        Get GitHub repository information.

        Args:
            repository: Repository identifier (e.g., "owner/repo")

        Returns:
            Repository object or None
        """
        try:
            return self.github_client.get_repo(repository)
        except Exception as e:
            self.log(f"Error getting repository {repository}: {e}", "ERROR")
            return None
