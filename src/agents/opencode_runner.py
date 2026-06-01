"""OpenCode runner for agent-based repository automation."""

import os
import random
import re
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

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
                ["opencode", "models"],
                capture_output=True,
                text=True,
                timeout=self.models_timeout,
            )
            if result.returncode != 0:
                self.log(
                    f"opencode models failed (rc={result.returncode}): {result.stderr}", "WARNING"
                )
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
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            ), None
        except subprocess.TimeoutExpired:
            return None, f"Command timed out after {timeout}s: {' '.join(cmd)}"
        except FileNotFoundError:
            return None, f"Command not found: {cmd[0]}"

    def _audit(
        self, emoji: str, status: str, repository: str, title: str, detail: str = ""
    ) -> None:
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

    def _build_branch_name(self, title: str) -> str:
        return (
            "agent/"
            + re.sub(r"[^a-z0-9-]", "-", title.lower())[:60]
            + "-"
            + datetime.now(UTC).strftime("%Y%m%d%H%M")
        )

    def _clone_repo(self, clone_url: str, tmpdir: str, title: str, repository: str) -> str | None:
        clone, clone_error = self._safe_subprocess_run(
            ["git", "clone", "--depth=1", clone_url, tmpdir],
            timeout=self.clone_timeout,
        )
        if clone_error:
            self.log(f"[{title}] git clone failed: {clone_error}", "ERROR")
            self._audit("❌", "clone_failed", repository, title, clone_error[:300])
            return clone_error[:300]
        clone_result = cast(subprocess.CompletedProcess[str], clone)
        if clone_result.returncode != 0:
            self.log(f"[{title}] git clone failed: {clone_result.stderr}", "ERROR")
            self._audit("❌", "clone_failed", repository, title, clone_result.stderr[:300])
            return clone_result.stderr[:300]
        return None

    def _configure_git(self, tmpdir: str, branch: str) -> None:
        subprocess.run(
            ["git", "config", "user.email", "github-assistance@github.com"],
            cwd=tmpdir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "github-assistance"], cwd=tmpdir, capture_output=True
        )
        # Get default/main branch name (typically main or master)
        default_branch = "main"
        try:
            res = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0 and res.stdout.strip():
                default_branch = res.stdout.strip()
        except Exception as e:
            self.log(f"Failed to detect default branch via git: {e}", "WARNING")

        # Explicitly pull remote main/default branch to guarantee it is up to date
        self.log(f"Pulling latest changes on branch '{default_branch}' from origin...")
        pull_res = subprocess.run(
            ["git", "pull", "origin", default_branch],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if pull_res.returncode != 0:
            self.log(
                f"git pull failed on branch '{default_branch}': {pull_res.stderr.strip()}",
                "WARNING",
            )

        subprocess.run(["git", "checkout", "-b", branch], cwd=tmpdir, capture_output=True)

    def _run_opencode_with_retry(
        self, tmpdir: str, instructions: str, title: str, repository: str, model: str
    ) -> tuple[subprocess.CompletedProcess[str] | None, str, str, str]:
        run_result = None
        used_model = model
        last_status = "opencode_failed"
        last_error = "Unknown opencode error"
        for attempt in range(self.max_attempts):
            current_model = model if attempt == 0 else "opencode/big-pickle"
            self.log(
                f"[{title}] Running opencode on {repository} (attempt {attempt + 1}/{self.max_attempts}; model: {current_model})..."
            )
            candidate_result, run_error = self._safe_subprocess_run(
                ["opencode", "run", "--model", current_model, instructions],
                timeout=self.run_timeout,
                cwd=tmpdir,
            )
            if run_error:
                last_error = run_error
                last_status = (
                    "opencode_timeout"
                    if run_error.startswith("Command timed out")
                    else "opencode_unavailable"
                )
                self.log(f"[{title}] opencode execution error: {run_error}", "WARNING")
            elif candidate_result and candidate_result.returncode == 0:
                run_result = candidate_result
                used_model = current_model
                break
            else:
                rc = candidate_result.returncode if candidate_result else "unknown"
                stderr = candidate_result.stderr if candidate_result else ""
                stdout = candidate_result.stdout if candidate_result else ""
                last_error = (stderr or stdout or f"opencode returned exit code {rc}")[:300]
                last_status = "opencode_failed"
                self.log(f"[{title}] opencode failed (rc={rc}): {last_error}", "WARNING")
        return run_result, used_model, last_status, last_error

    def _commit_changes(
        self, tmpdir: str, title: str, agent_name: str, used_model: str
    ) -> str | None:
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        commit = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"feat: {title}\n\nApplied by github-assistance agent `{agent_name}` via opencode ({used_model}).",
            ],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        if "nothing to commit" in commit.stdout + commit.stderr:
            return "no_changes"
        return None

    def _push_branch(self, tmpdir: str, title: str, repository: str, branch: str) -> str | None:
        push, push_error = self._safe_subprocess_run(
            ["git", "push", "origin", branch],
            timeout=self.push_timeout,
            cwd=tmpdir,
        )
        if push_error:
            self.log(f"[{title}] git push failed: {push_error}", "ERROR")
            self._audit("❌", "push_failed", repository, title, push_error[:300])
            return push_error[:300]
        push_result = cast(subprocess.CompletedProcess[str], push)
        if push_result.returncode != 0:
            self.log(f"[{title}] git push failed: {push_result.stderr}", "ERROR")
            self._audit("❌", "push_failed", repository, title, push_result.stderr[:300])
            return push_result.stderr[:300]
        return None

    def run_on_repo(
        self, repository: str, instructions: str, title: str, agent_name: str = "agent"
    ) -> dict:
        """Clone repo, run opencode on a new branch, commit, push and open a PR."""
        if not self.allowlist.is_allowed(repository):
            raise ValueError(f"opencode denied: Repository {repository} is not in allowlist")

        # Check if there is already an open PR or a recently created PR for this agent and task
        try:
            repo = self.github_client.get_repo(repository)
            expected_title = f"[agent/{agent_name}] {title}"

            # Check open PRs first
            for pr in repo.get_pulls(state="open"):
                if pr.title == expected_title:
                    self.log(f"[{title}] Pull request already exists and is open: {pr.html_url}")
                    self._audit("ℹ️", "pr_already_exists", repository, title, pr.html_url)
                    return {
                        "status": "skipped",
                        "pr_url": pr.html_url,
                        "reason": "pr_already_exists",
                    }

            # Check recently closed PRs (e.g. in the last 24 hours) to avoid rapid re-runs
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            for raw_pr in repo.get_pulls(state="closed")[:10]:
                pr = cast(Any, raw_pr)
                if (
                    pr.title == expected_title
                    and pr.created_at
                    and pr.created_at.replace(tzinfo=UTC) > cutoff
                ):
                    self.log(
                        f"[{title}] Pull request for this task was recently created and closed/merged (PR #{pr.number}). Cooldown active."
                    )
                    self._audit("ℹ️", "pr_cooldown_active", repository, title, pr.html_url)
                    return {
                        "status": "skipped",
                        "pr_url": pr.html_url,
                        "reason": "pr_cooldown_active",
                    }
        except Exception as e:
            self.log(f"Failed to check for existing/recent PRs on {repository}: {e}", "WARNING")

        model = self.get_random_free_opencode_model()
        github_token = os.getenv("GITHUB_TOKEN", "")
        clone_url = f"https://{github_token}@github.com/{repository}.git"
        branch = self._build_branch_name(title)

        self._audit("🚀", "iniciando", repository, title)

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_error = self._clone_repo(clone_url, tmpdir, title, repository)
            if clone_error:
                return {"status": "clone_failed", "error": clone_error}
            self._configure_git(tmpdir, branch)

            run_result, used_model, last_status, last_error = self._run_opencode_with_retry(
                tmpdir, instructions, title, repository, model
            )
            if not run_result:
                self._audit("❌", last_status, repository, title, last_error[:300])
                return {"status": last_status, "stderr": last_error[:300], "model": used_model}

            no_changes = self._commit_changes(tmpdir, title, agent_name, used_model)
            if no_changes:
                self.log(f"[{title}] opencode made no changes.")
                self._audit("ℹ️", "no_changes", repository, title)
                return {"status": "no_changes"}

            push_error = self._push_branch(tmpdir, title, repository, branch)
            if push_error:
                return {"status": "push_failed", "error": push_error}

        pr_url = self._open_pull_request(
            repository, branch, title, run_result.stdout, agent_name, used_model
        )
        self.log(f"[{title}] PR opened: {pr_url}")
        self._audit("✅", "pr_aberto", repository, title, pr_url)
        return {
            "status": "success",
            "branch": branch,
            "pr_url": pr_url,
            "model": used_model,
            "agent": agent_name,
        }

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
        pr = repo.create_pull(
            title=f"[agent/{agent_name}] {title}", body=body, head=branch, base=base
        )
        return pr.html_url
