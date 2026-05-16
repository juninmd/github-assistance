"""
Base Agent class for all development agents.
"""
from abc import ABC, abstractmethod
from typing import Any

from github.Repository import Repository as GhRepository

from src.agents import utils
from src.agents.jules_manager import JulesSessionManager
from src.agents.opencode_runner import OpencodeRunner
from src.agents.repo_manager import RepositoryManager
from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier
from src.utils.logger import StructuredLogger, get_logger


class BaseAgent(ABC):
    """
    Abstract base class for all development agents.
    """

    def __init__(
        self,
        jules_client: JulesClient,
        github_client: GithubClient,
        allowlist: RepositoryAllowlist,
        telegram: TelegramNotifier | None = None,
        name: str = "BaseAgent",
        enforce_repository_allowlist: bool = False,
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
        self._logger: StructuredLogger = get_logger(name)
        self._repo_mgr = RepositoryManager(github_client, allowlist, target_owner, self.log)
        self._jules_mgr = JulesSessionManager(jules_client, self.log)
        self._opencode = OpencodeRunner(allowlist, self.log, github_client)

    @property
    @abstractmethod
    def persona(self) -> str:
        pass

    @property
    @abstractmethod
    def mission(self) -> str:
        pass

    def load_instructions(self) -> str:
        if self._instructions_cache:
            return self._instructions_cache
        self._instructions_cache = utils.load_instructions(self.name, self.log)
        return self._instructions_cache

    def load_jules_instructions(
        self,
        template_name: str = "jules-instructions.md",
        variables: dict[str, Any] | None = None,
    ) -> str:
        return utils.load_jules_instructions(self.name, template_name, variables, self.log)

    def get_instructions_section(self, section_header: str) -> str:
        return utils.get_instructions_section(self.load_instructions(), section_header)

    def get_allowed_repositories(self) -> list[str]:
        return self._repo_mgr.get_allowed_repositories(self.enforce_repository_allowlist)

    def uses_repository_allowlist(self) -> bool:
        return self.enforce_repository_allowlist

    def can_work_on_repository(self, repository: str) -> bool:
        return self._repo_mgr.can_work_on(repository, self.enforce_repository_allowlist)

    @abstractmethod
    def run(self) -> dict[str, Any]:
        pass

    def check_rate_limit(self) -> int:
        return utils.check_github_rate_limit(self.github_client, self.log)

    def log(self, message: str, level: str = "INFO") -> None:
        self._logger(message, level)

    def has_recent_jules_session(self, repository: str, task_keyword: str = "", hours: int = 24) -> bool:
        return utils.has_recent_jules_session(
            self.jules_client, repository, task_keyword, hours, self.log
        )

    def create_jules_session(
        self,
        repository: str,
        instructions: str,
        title: str,
        wait_for_completion: bool = False,
        base_branch: str | None = None,
    ) -> dict[str, Any]:
        if not self.allowlist.is_allowed(repository):
            raise ValueError(f"Jules session denied: Repository {repository} is not in allowlist")
        if not base_branch:
            repo_info = self.get_repository_info(repository)
            if not repo_info or not hasattr(repo_info, "default_branch"):
                raise ValueError(f"Could not determine default branch for {repository}")
            base_branch = repo_info.default_branch
        prompt = f"# GITHUB ASSISTANCE AGENT CONTEXT\nAgent: {self.name}\n" \
                 f"Persona: {self.persona}\nMission: {self.mission}\n\n" \
                 f"# TASK INSTRUCTIONS\n{instructions}"
        return self._jules_mgr.create_session(
            repository=repository, prompt=prompt, title=title,
            base_branch=base_branch, wait_for_completion=wait_for_completion,
        )

    def get_repository_info(self, repository: str) -> GhRepository | None:
        return self._repo_mgr.get_info(repository)

    def run_opencode_on_repo(self, repository: str, instructions: str, title: str) -> dict[str, Any]:
        return self._opencode.run_on_repo(repository, instructions, title)

    def _get_random_free_opencode_model(self) -> str:
        return self._opencode.get_random_free_opencode_model()

