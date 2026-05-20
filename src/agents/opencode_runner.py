"""OpenCode runner for agent-based repository automation."""
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from typing import cast

from src.agents import utils as agent_utils
from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.notifications.telegram import TelegramNotifier


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


class OpencodeRunner:
    """Handles opencode-based repository operations."""

    def __init__(
        self,
        allowlist: RepositoryAllowlist,
        log_func: Callable[..., None],
        github_client: GithubClient,
        telegram: TelegramNotifier | None = None,
    ) -> None:
        self.allowlist = allowlist
        self.log = log_func
        self.github_client = github_client
        self.telegram = telegram or TelegramNotifier()
        self.models_timeout = _env_int("OPENCODE_MODELS_TIMEOUT_SECONDS", 20)
        self.clone_timeout = _env_int("OPENCODE_CLONE_TIMEOUT_SECONDS", 120)
        self.warmup_timeout = _env_int("OPENCODE_WARMUP_TIMEOUT_SECONDS", 180)
        self.run_timeout = _env_int("OPENCODE_RUN_TIMEOUT_SECONDS", 1200)
        self.push_timeout = _env_int("OPENCODE_PUSH_TIMEOUT_SECONDS", 120)
        self.max_attempts = _env_int("OPENCODE_RUN_MAX_ATTEMPTS", 2)

    def get_random_free_opencode_model(self) -> str:
        return agent_utils.get_free_opencode_model(
            log_func=self.log,
            timeout=self.models_timeout,
        )

    def _safe_subprocess_run(
        self, cmd: list[str], timeout: int, cwd: str | None = None
    ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
            ), None
        except subprocess.TimeoutExpired:
            return None, f"Command timed out after {timeout}s: {' '.join(cmd)}"
        except FileNotFoundError:
            return None, f"Command not found: {cmd[0]}"

    def _audit(self, emoji: str, status: str, repository: str, title: str, detail: str = "") -> None:
        text = (
            f"{emoji} <b>github-assistance audit</b>\n"
            f"──────────────────────\n"
            f"📦 <b>Repo:</b> <code>{repository}</code>\n"
            f"🏷 <b>Tarefa:</b> {title}\n"
            f"📊 <b>Status:</b> <code>{status}</code>"
        )
        if detail:
            text += f"\n⚠️ <pre>{detail[:300]}</pre>"
        self.telegram.send_message(text)

    def _report_failure(self, status: str, repository: str, title: str, error: str) -> dict:
        self.log(f"[{title}] {status}: {error[:300]}", "ERROR")
        self._audit("❌", status, repository, title, error[:300])
        return {"status": status, "error": error[:300]}

    def _clone_and_setup(self, repository: str, title: str, tmpdir: str) -> tuple[str, str] | dict:
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = f"https://{github_token}@github.com/{repository}.git"
        branch = "agent/" + re.sub(r"[^a-z0-9-]", "-", title.lower())[:60] + "-" + datetime.now().strftime("%Y%m%d%H%M")

        clone, clone_error = self._safe_subprocess_run(
            ["git", "clone", "--depth=1", clone_url, tmpdir],
            timeout=self.clone_timeout,
        )
        if clone_error:
            return self._report_failure("clone_failed", repository, title, clone_error)
        clone_result = cast(subprocess.CompletedProcess[str], clone)
        if clone_result.returncode != 0:
            return self._report_failure("clone_failed", repository, title, clone_result.stderr)

        agent_utils.setup_git_config(tmpdir, user_email="github-assistance@github.com", user_name="github-assistance")
        subprocess.run(["git", "checkout", "-b", branch], cwd=tmpdir, capture_output=True)

        return clone_url, branch

    def _warmup_opencode(self, model: str, title: str, tmpdir: str) -> None:
        self.log(f"[{title}] Warming up opencode...")
        _, warmup_error = self._safe_subprocess_run(
            ["opencode", "run", "--model", model, "ping"],
            timeout=self.warmup_timeout, cwd=tmpdir,
        )
        if warmup_error:
            self.log(f"[{title}] warmup skipped: {warmup_error}", "WARNING")

    def _run_opencode_with_retry(
        self, model: str, instructions: str, title: str, repository: str, tmpdir: str
    ) -> tuple[subprocess.CompletedProcess[str] | None, str]:
        for attempt in range(self.max_attempts):
            current_model = model if attempt == 0 else "opencode/big-pickle"
            self.log(
                f"[{title}] Running opencode on {repository} "
                f"(attempt {attempt + 1}/{self.max_attempts}; model: {current_model})..."
            )
            candidate_result, run_error = self._safe_subprocess_run(
                ["opencode", "run", "--model", current_model, instructions],
                timeout=self.run_timeout, cwd=tmpdir,
            )
            if run_error:
                self.log(f"[{title}] opencode execution error: {run_error}", "WARNING")
                if attempt < self.max_attempts - 1:
                    continue
                return candidate_result, run_error
            if candidate_result and candidate_result.returncode == 0:
                return candidate_result, current_model
            rc = candidate_result.returncode if candidate_result else "unknown"
            stderr = candidate_result.stderr if candidate_result else ""
            stdout = candidate_result.stdout if candidate_result else ""
            error = (stderr or stdout or f"opencode returned exit code {rc}")[:300]
            self.log(f"[{title}] opencode failed (rc={rc}): {error}", "WARNING")
        return None, "All opencode attempts failed"

    def _commit_and_push(
        self, tmpdir: str, branch: str, title: str, repository: str, agent_name: str, used_model: str
    ) -> dict | None:
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        commit = subprocess.run(
            ["git", "commit", "-m", f"feat: {title}\n\nApplied by github-assistance agent `{agent_name}` via opencode ({used_model})."],
            cwd=tmpdir, capture_output=True, text=True,
        )
        if "nothing to commit" in commit.stdout + commit.stderr:
            self.log(f"[{title}] opencode made no changes.")
            self._audit("ℹ️", "no_changes", repository, title)
            return {"status": "no_changes"}

        push, push_error = self._safe_subprocess_run(
            ["git", "push", "origin", branch],
            timeout=self.push_timeout, cwd=tmpdir,
        )
        if push_error:
            return self._report_failure("push_failed", repository, title, push_error)
        push_result = cast(subprocess.CompletedProcess[str], push)
        if push_result.returncode != 0:
            return self._report_failure("push_failed", repository, title, push_result.stderr)
        return None

    def run_on_repo(self, repository: str, instructions: str, title: str, agent_name: str = "agent") -> dict:
        if not self.allowlist.is_allowed(repository):
            raise ValueError(f"opencode denied: Repository {repository} is not in allowlist")

        model = self.get_random_free_opencode_model()
        self._audit("🚀", "iniciando", repository, title)

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_result = self._clone_and_setup(repository, title, tmpdir)
            if isinstance(setup_result, dict):
                return setup_result
            _, branch = setup_result

            self._warmup_opencode(model, title, tmpdir)

            run_result, used_model = self._run_opencode_with_retry(model, instructions, title, repository, tmpdir)
            if run_result is None:
                audit_status = "opencode_timeout" if "timed out" in used_model else "opencode_failed"
                return self._report_failure(audit_status, repository, title, used_model)

            push_result = self._commit_and_push(tmpdir, branch, title, repository, agent_name, used_model)
            if isinstance(push_result, dict):
                return push_result

        pr_url = self._open_pull_request(repository, branch, title, run_result.stdout, agent_name, used_model)
        self.log(f"[{title}] PR opened: {pr_url}")
        self._audit("✅", "pr_aberto", repository, title, pr_url)
        return {"status": "success", "branch": branch, "pr_url": pr_url, "model": used_model, "agent": agent_name}

    def _open_pull_request(
        self,
        repository: str,
        branch: str,
        title: str,
        opencode_output: str,
        agent_name: str = "agent",
        model: str = "opencode",
    ) -> str:
        repo = self.github_client.get_repo(repository)
        base = repo.default_branch
        body = agent_utils.build_pr_body(agent_name, title, opencode_output, model)
        pr = repo.create_pull(title=f"[agent/{agent_name}] {title}", body=body, head=branch, base=base)
        return pr.html_url
