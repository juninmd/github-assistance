"""OpenCode runner for agent-based repository automation."""
import os
import random
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
    """Read an integer env var, returning a bounded default when value is missing/invalid."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


class OpencodeRunner:
    """Handles opencode-based repository operations."""

    _model_cache: str | None = None

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
        self.run_timeout = _env_int("OPENCODE_RUN_TIMEOUT_SECONDS", 1200)
        self.push_timeout = _env_int("OPENCODE_PUSH_TIMEOUT_SECONDS", 120)
        self.max_attempts = _env_int("OPENCODE_RUN_MAX_ATTEMPTS", 2)

    def get_random_free_opencode_model(self) -> str:
        """Pick a random free opencode model. Falls back to big-pickle on failure."""
        if OpencodeRunner._model_cache is not None:
            return OpencodeRunner._model_cache
        try:
            result = subprocess.run(
                ["opencode", "models"], capture_output=True, text=True, timeout=self.models_timeout,
            )
            if result.returncode != 0:
                self.log(f"opencode models failed (rc={result.returncode}): {result.stderr}", "WARNING")
                OpencodeRunner._model_cache = "opencode/big-pickle"
                return OpencodeRunner._model_cache
            models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
            free = [m for m in models if m.endswith("-free") or m == "opencode/big-pickle"]
            if free:
                chosen = random.choice(free)
                self.log(f"Selected free opencode model: {chosen}")
                OpencodeRunner._model_cache = chosen
                return chosen
        except Exception as e:
            self.log(f"Could not list opencode models: {e}", "WARNING")
        OpencodeRunner._model_cache = "opencode/big-pickle"
        return OpencodeRunner._model_cache

    def _safe_subprocess_run(
        self, cmd: list[str], timeout: int, cwd: str | None = None
    ) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
        """Run subprocess with timeout and return either result or a normalized error message."""
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

    def run_on_repo(self, repository: str, instructions: str, title: str, agent_name: str = "agent") -> dict:
        """Clone repo, run opencode on a new branch, commit, push and open a PR."""
        if not self.allowlist.is_allowed(repository):
            raise ValueError(f"opencode denied: Repository {repository} is not in allowlist")

        model = self.get_random_free_opencode_model()
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = f"https://{github_token}@github.com/{repository}.git"
        branch = "agent/" + re.sub(r"[^a-z0-9-]", "-", title.lower())[:60] + "-" + datetime.now().strftime("%Y%m%d%H%M")

        self._audit("🚀", "iniciando", repository, title)

        with tempfile.TemporaryDirectory() as tmpdir:
            clone, clone_error = self._safe_subprocess_run(
                ["git", "clone", "--depth=1", clone_url, tmpdir],
                timeout=self.clone_timeout,
            )
            if clone_error:
                self.log(f"[{title}] git clone failed: {clone_error}", "ERROR")
                self._audit("❌", "clone_failed", repository, title, clone_error[:300])
                return {"status": "clone_failed", "error": clone_error[:300]}
            clone_result = cast(subprocess.CompletedProcess[str], clone)
            if clone_result.returncode != 0:
                self.log(f"[{title}] git clone failed: {clone_result.stderr}", "ERROR")
                self._audit("❌", "clone_failed", repository, title, clone_result.stderr[:300])
                return {"status": "clone_failed", "error": clone_result.stderr[:300]}

            subprocess.run(["git", "config", "user.email", "github-assistance@github.com"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "github-assistance"], cwd=tmpdir, capture_output=True)
            subprocess.run(["git", "checkout", "-b", branch], cwd=tmpdir, capture_output=True)

            run_result: subprocess.CompletedProcess[str] | None = None
            used_model = model
            last_status = "opencode_failed"
            last_error = "Unknown opencode error"
            total_attempts = self.max_attempts
            for attempt in range(total_attempts):
                current_model = model if attempt == 0 else "opencode/big-pickle"
                self.log(
                    f"[{title}] Running opencode on {repository} (attempt {attempt + 1}/{total_attempts}; model: {current_model})..."
                )
                candidate_result, run_error = self._safe_subprocess_run(
                    ["opencode", "run", "--model", current_model, instructions],
                    timeout=self.run_timeout, cwd=tmpdir,
                )
                if run_error:
                    last_error = run_error
                    last_status = "opencode_timeout" if run_error.startswith("Command timed out") else "opencode_unavailable"
                    self.log(f"[{title}] opencode execution error: {run_error}", "WARNING")
                elif candidate_result and candidate_result.returncode == 0:
                    run_result = candidate_result
                    used_model = current_model
                    break
                else:
                    rc = candidate_result.returncode if candidate_result else "unknown"
                    stderr = candidate_result.stderr if candidate_result else ""
                    stdout = candidate_result.stdout if candidate_result else ""
                    default_error_msg = f"opencode returned exit code {rc}"
                    last_error = (stderr or stdout or default_error_msg)[:300]
                    last_status = "opencode_failed"
                    self.log(f"[{title}] opencode failed (rc={rc}): {last_error}", "WARNING")

            if not run_result:
                self._audit("❌", last_status, repository, title, last_error[:300])
                return {"status": last_status, "stderr": last_error[:300], "model": used_model}

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
                self.log(f"[{title}] git push failed: {push_error}", "ERROR")
                self._audit("❌", "push_failed", repository, title, push_error[:300])
                return {"status": "push_failed", "error": push_error[:300]}
            push_result = cast(subprocess.CompletedProcess[str], push)
            if push_result.returncode != 0:
                self.log(f"[{title}] git push failed: {push_result.stderr}", "ERROR")
                self._audit("❌", "push_failed", repository, title, push_result.stderr[:300])
                return {"status": "push_failed", "error": push_result.stderr[:300]}

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
        """Open a pull request for the given branch and return the PR URL."""
        repo = self.github_client.get_repo(repository)
        base = repo.default_branch
        body = agent_utils.build_pr_body(agent_name, title, opencode_output, model)
        pr = repo.create_pull(title=f"[agent/{agent_name}] {title}", body=body, head=branch, base=base)
        return pr.html_url
