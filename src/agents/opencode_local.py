"""Run opencode locally against a repository: clone, implement, push, open a PR.

Replaces the previous vibe-code delegation. Everything happens on the runner:
the repo is cloned into a temp dir, opencode applies the changes, and a PR is
opened from a fresh branch when the working tree is dirty.
"""

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.agents.commit_message import semantic_message
from src.agents.opencode_models import select_free_opencode_model
from src.agents.utils import assign_owner, build_pr_body, request_review_owner
from src.utils.proc import run as proc_run

_OPENCODE_TIMEOUT = 1200
_GIT_TIMEOUT = 300


def _opencode_cmd() -> str:
    return shutil.which("opencode") or "opencode"


def _redact(text: str | None) -> str:
    return re.sub(r"x-access-token:[^@]+@", "x-access-token:REDACTED@", text or "").strip()


def _run_git(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    result = proc_run(cmd, cwd=cwd, capture_output=True, text=True, timeout=_GIT_TIMEOUT)
    if result.returncode != 0:
        safe = [re.sub(r"x-access-token:[^@]+@", "x-access-token:REDACTED@", a) for a in cmd]
        raise subprocess.CalledProcessError(
            result.returncode, safe, result.stdout, _redact(result.stderr)
        )
    return result


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:48] or "task"


def _result(status: str, repository: str, **extra: Any) -> dict[str, Any]:
    base = {
        "status": status,
        "task_url": None,
        "task_id": None,
        "engine": "opencode-local",
        "repository": repository,
    }
    base.update(extra)
    return base


def run_opencode_task(
    github_client: Any,
    repository: str,
    instructions: str,
    title: str,
    base_branch: str,
    log: Callable[[str, str], None],
    agent_name: str = "github-assistance",
) -> dict[str, Any]:
    """Clone the repo, run opencode, push a branch, and open a PR.

    Returns a dict mirroring the old vibe-code contract: ``status`` is
    ``"task_created"`` when a PR is opened, otherwise ``"no_changes"`` or a
    failure reason. ``task_url``/``task_id`` carry the PR URL/number.
    """
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    if not token:
        return _result("failed", repository, error="missing GITHUB_TOKEN")
    clone_url = f"https://x-access-token:{token}@github.com/{repository}.git"
    branch = f"opencode/{_slugify(title)}"

    try:
        with tempfile.TemporaryDirectory() as tmp:
            clone_dir = str(Path(tmp) / "repo")
            _run_git(["git", "clone", "--depth=1", clone_url, clone_dir], cwd=tmp)
            _run_git(
                ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
                cwd=clone_dir,
            )
            _run_git(["git", "config", "user.name", "github-actions[bot]"], cwd=clone_dir)
            _run_git(["git", "checkout", "-b", branch], cwd=clone_dir)

            env = os.environ.copy()
            if "NODE_OPTIONS" not in env:
                env["NODE_OPTIONS"] = "--max-old-space-size=2048"
            if "NODE_ENV" not in env:
                env["NODE_ENV"] = "production"

            max_attempts = int(os.getenv("OPENCODE_RUN_MAX_ATTEMPTS", "2"))
            oc: subprocess.CompletedProcess[str] | None = None
            used_model = select_free_opencode_model(0)
            for attempt in range(max_attempts):
                current_model = select_free_opencode_model(attempt)
                used_model = current_model
                log(f"Running opencode ({attempt + 1}/{max_attempts}; model: {current_model})", "INFO")
                oc = proc_run(
                    [_opencode_cmd(), "run", "--model", current_model, instructions],
                    cwd=clone_dir,
                    capture_output=True,
                    text=True,
                    timeout=_OPENCODE_TIMEOUT,
                    env=env,
                )
                if oc.returncode == 0:
                    break
                log(f"opencode failed with {current_model}: {_redact(oc.stderr)[:200]}", "WARNING")

            if not oc or oc.returncode != 0:
                err = _redact(oc.stderr if oc else "unknown")[:300]
                log(f"opencode failed for {repository}: {err}", "WARNING")
                return _result("opencode_failed", repository, error="opencode run failed")

            status = proc_run(
                ["git", "status", "--porcelain"],
                cwd=clone_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if not status.stdout.strip():
                log(f"opencode made no changes for {repository}", "INFO")
                return _result("no_changes", repository)

            _run_git(["git", "add", "-A"], cwd=clone_dir)
            _run_git(
                ["git", "commit", "-m", semantic_message("chore", "opencode", title)],
                cwd=clone_dir,
            )
            _run_git(["git", "push", "origin", branch], cwd=clone_dir)
    except subprocess.TimeoutExpired:
        return _result("failed", repository, error="opencode/git timed out")
    except subprocess.CalledProcessError as exc:
        return _result("failed", repository, error=f"git failed: {_redact(str(exc.stderr))[:200]}")
    except Exception as exc:
        log(f"opencode local run errored for {repository}: {type(exc).__name__}", "WARNING")
        return _result("failed", repository, error=type(exc).__name__)

    try:
        repo = github_client.get_repo(repository)
        pr_body = build_pr_body(
            agent_name=agent_name,
            title=title,
            opencode_output=instructions,
            model=used_model,
        )
        pr = repo.create_pull(
            title=title,
            body=pr_body,
            head=branch,
            base=base_branch,
        )
        assign_owner(pr, log_func=log)
        request_review_owner(pr, log_func=log)
    except Exception as exc:
        log(f"Failed to open PR for {repository}: {type(exc).__name__}", "WARNING")
        return _result("failed", repository, error=f"pr creation failed: {type(exc).__name__}")

    log(f"Opened PR #{pr.number} for {repository} via opencode", "INFO")
    return _result("task_created", repository, task_url=pr.html_url, task_id=pr.number)
