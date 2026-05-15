"""
Base Agent class for all development agents.
"""
import os
import random
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Any

from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier
from src.agents import utils
from src.agents.jules_manager import JulesSessionManager
from src.agents.repo_manager import RepositoryManager
from src.utils.logger import StructuredLogger, get_logger


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
        
        # Specialized managers
        self._repo_mgr = RepositoryManager(github_client, allowlist, target_owner, self.log)
        self._jules_mgr = JulesSessionManager(jules_client, self.log)
        self._jules_sessions_cache: list[dict] | None = None
        self._opencode_model_cache: str | None = None

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
        """Load Jules task instructions from markdown template."""
        return utils.load_jules_instructions(self.name, template_name, variables, self.log)

    def get_instructions_section(self, section_header: str) -> str:
        """Extract a specific section from instructions markdown."""
        return utils.get_instructions_section(self.load_instructions(), section_header)

    def get_allowed_repositories(self) -> list[str]:
        return self._repo_mgr.get_allowed_repositories(self.enforce_repository_allowlist)

    def uses_repository_allowlist(self) -> bool:
        return self.enforce_repository_allowlist

    def can_work_on_repository(self, repository: str) -> bool:
        return self._repo_mgr.can_work_on(repository, self.enforce_repository_allowlist)

    @abstractmethod
    def run(self) -> dict[str, Any]:
        pass  # pragma: no cover

    def check_rate_limit(self) -> int:
        return utils.check_github_rate_limit(self.github_client, self.log)

    def log(self, message: str, level: str = "INFO") -> None:
        self._logger(message, level)

    def has_recent_jules_session(self, repository: str, task_keyword: str = "", hours: int = 24) -> bool:
        if self._jules_sessions_cache is None:
            try:
                self._jules_sessions_cache = self.jules_client.list_sessions(page_size=100)
            except Exception:
                return utils.has_recent_jules_session(
                    self.jules_client, repository, task_keyword, hours, self.log,
                )
        return utils.has_recent_jules_session(
            self.jules_client, repository, task_keyword, hours, self.log,
            cached_sessions=self._jules_sessions_cache,
        )

    def create_jules_session(
        self,
        repository: str,
        instructions: str,
        title: str,
        wait_for_completion: bool = False,
        base_branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a Jules session with agent's persona context."""
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
            repository=repository,
            prompt=prompt,
            title=title,
            base_branch=base_branch,
            wait_for_completion=wait_for_completion,
        )

    def get_repository_info(self, repository: str) -> Any | None:
        return self._repo_mgr.get_info(repository)

    def _get_random_free_opencode_model(self) -> str:
        """Pick a random free opencode model. Falls back to big-pickle on failure."""
        if self._opencode_model_cache:
            return self._opencode_model_cache
        try:
            result = subprocess.run(
                ["opencode", "models"], capture_output=True, text=True, timeout=15,
            )
            models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
            free = [m for m in models if m.endswith("-free") or m == "opencode/big-pickle"]
            if free:
                chosen = random.choice(free)
                self.log(f"Selected free opencode model: {chosen}")
                self._opencode_model_cache = chosen
                return chosen
        except Exception as e:
            self.log(f"Could not list opencode models: {e}", "WARNING")
        self._opencode_model_cache = "opencode/big-pickle"
        return self._opencode_model_cache

    def _clone_and_setup_branch(self, repository, title, branch, tmpdir):
        """Clone repository and create a working branch. Returns clone_url or None on failure."""
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = f"https://{github_token}@github.com/{repository}.git"
        clone = subprocess.run(
            ["git", "clone", "--depth=1", clone_url, tmpdir],
            capture_output=True, text=True, timeout=60,
        )
        if clone.returncode != 0:
            self.log(f"[{title}] git clone failed: {clone.stderr}", "ERROR")
            return None

        subprocess.run(["git", "config", "user.email", "github-assistance@github.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "github-assistance"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", branch], cwd=tmpdir, capture_output=True)
        return clone_url

    def _run_opencode(self, model, instructions, title, tmpdir, branch, repository):
        """Run opencode on the cloned repo. Returns result or None on failure."""
        self.log(f"[{title}] Warming up opencode...")
        subprocess.run(
            ["opencode", "run", "--model", model, "ping"],
            capture_output=True, text=True, timeout=120, cwd=tmpdir,
        )
        self.log(f"[{title}] Running opencode on {repository} (branch: {branch})...")
        run_result = subprocess.run(
            ["opencode", "run", "--model", model, instructions],
            capture_output=True, text=True, timeout=600, cwd=tmpdir,
        )
        if run_result.returncode != 0:
            self.log(f"[{title}] opencode failed (rc={run_result.returncode}): {run_result.stderr}", "WARNING")
            return None
        return run_result

    def _commit_and_push(self, title, branch, tmpdir):
        """Commit and push changes. Returns True on success."""
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        commit = subprocess.run(
            ["git", "commit", "-m", f"feat: {title}\n\nApplied by github-assistance senior_developer agent via opencode."],
            cwd=tmpdir, capture_output=True, text=True,
        )
        if "nothing to commit" in commit.stdout + commit.stderr:
            self.log(f"[{title}] opencode made no changes.")
            return False

        push = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=tmpdir, capture_output=True, text=True, timeout=60,
        )
        if push.returncode != 0:
            self.log(f"[{title}] git push failed: {push.stderr}", "ERROR")
            raise RuntimeError(push.stderr[:300])
        return True

    def run_opencode_on_repo(self, repository: str, instructions: str, title: str) -> dict[str, Any]:
        """Clone repo, run opencode on a new branch, commit, push and open a pull request."""
        if not self.allowlist.is_allowed(repository):
            raise ValueError(f"opencode denied: Repository {repository} is not in allowlist")

        import re as _re
        from datetime import datetime as _dt

        model = self._get_random_free_opencode_model()
        branch = "agent/" + _re.sub(r"[^a-z0-9-]", "-", title.lower())[:60] + "-" + _dt.now().strftime("%Y%m%d%H%M")

        with tempfile.TemporaryDirectory() as tmpdir:
            if not self._clone_and_setup_branch(repository, title, branch, tmpdir):
                return {"status": "clone_failed"}

            run_result = self._run_opencode(model, instructions, title, tmpdir, branch, repository)
            if run_result is None:
                return {"status": "opencode_failed"}

            try:
                if not self._commit_and_push(title, branch, tmpdir):
                    return {"status": "no_changes"}
            except RuntimeError as e:
                return {"status": "push_failed", "error": str(e)}

        pr_url = self._open_pull_request(repository, branch, title, run_result.stdout)
        self.log(f"[{title}] PR opened: {pr_url}")
        return {"status": "success", "branch": branch, "pr_url": pr_url}

    def _open_pull_request(self, repository: str, branch: str, title: str, opencode_output: str) -> str:
        """Open a pull request for the given branch and return the PR URL."""
        repo = self.github_client.get_repo(repository)
        base = repo.default_branch
        body = (
            f"## 🤖 Alterações aplicadas pelo agente `senior_developer`\n\n"
            f"**Modelo utilizado:** opencode (free tier)\n\n"
            f"### O que foi feito\n"
            f"{title}\n\n"
            f"### Saída do opencode\n"
            f"```\n{opencode_output[:1500]}\n```\n\n"
            f"---\n_Pull request criado automaticamente pelo agente github-assistance._"
        )
        pr = repo.create_pull(title=f"[agent] {title}", body=body, head=branch, base=base)
        return pr.html_url

