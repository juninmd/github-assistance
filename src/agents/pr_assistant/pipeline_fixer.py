"""Autonomous GitHub Actions pipeline fixing for the conflict-resolution flow.

After a PR's CI fails, this clones the head branch, feeds the real error logs to
opencode, validates the edit, and pushes a fix. Attempts are tracked across agent
runs via a marker comment so the pipeline can re-run between attempts.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from github.PullRequest import PullRequest

from src.agents.pr_assistant.conflict_resolver import (
    _OPENCODE_RESOLUTION_TIMEOUT,
    _get_free_opencode_models,
    _opencode_cmd,
    _run_git,
    _setup_clone_environment,
)

DEFAULT_MAX_ATTEMPTS = 3
MANUAL_PIPELINE_LABEL = "needs-manual-pipeline-fix"

# Marker embedded in the bot's attempt comment so we can read state across runs.
_MARKER_RE = re.compile(r"<!--\s*pipeline-fix\s+attempt=(\d+)\s+sha=([0-9a-fA-F]+)\s*-->")


def pipeline_fix_enabled() -> bool:
    return os.getenv("PIPELINE_FIX_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def max_attempts() -> int:
    try:
        return max(1, int(os.getenv("PIPELINE_FIX_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS))))
    except ValueError:
        return DEFAULT_MAX_ATTEMPTS


def build_marker(attempt: int, sha: str) -> str:
    return f"<!-- pipeline-fix attempt={attempt} sha={sha} -->"


def read_attempt_state(comments: list) -> tuple[int, str]:
    """Return (last_attempt, last_sha) from the most recent marker comment."""
    last_attempt = 0
    last_sha = ""
    for comment in comments:
        match = _MARKER_RE.search(getattr(comment, "body", "") or "")
        if match:
            last_attempt = int(match.group(1))
            last_sha = match.group(2)
    return last_attempt, last_sha


def _build_prompt(error_logs: str, failed_checks: list[str]) -> str:
    checks = ", ".join(failed_checks) or "unknown checks"
    return (
        "You are an expert software engineer fixing a failing CI pipeline.\n"
        f"The following GitHub Actions checks are failing: {checks}.\n"
        "Below are the error logs from the failed jobs.\n"
        "Apply the MINIMAL, SAFE change to the source/config files in this repository so the\n"
        "pipeline passes. Do not introduce unrelated changes, new features, or disable tests.\n"
        "Edit the files directly in the working tree.\n\n"
        "Error logs:\n"
        f"{error_logs}"
    )


def _changed_files(clone_dir: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def _summarize_opencode_output(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines[-6:])[:500]


def _run_opencode_fix(clone_dir: str, prompt: str) -> tuple[str, str]:
    """Run opencode agentically in the clone dir. Returns (model used, error)."""
    last_error = ""
    for model in _get_free_opencode_models():
        try:
            result = subprocess.run(
                [_opencode_cmd(), "run", "--model", model, prompt],
                cwd=clone_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_OPENCODE_RESOLUTION_TIMEOUT,
            )
            if result.returncode == 0:
                return f"opencode/{model}", ""
            output = _summarize_opencode_output(
                (result.stderr or "") + "\n" + (result.stdout or "")
            )
            last_error = f"{model} exited {result.returncode}: {output}"
        except (subprocess.SubprocessError, OSError) as exc:
            last_error = f"{model} failed to execute: {type(exc).__name__}: {exc}"
            continue
    return "", last_error


def _validate_changes(clone_dir: str, changed: list[str]) -> tuple[bool, str]:
    """Lightweight sanity checks on the opencode edit before pushing."""
    diff_check = subprocess.run(
        ["git", "diff", "--check"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if diff_check.returncode != 0:
        output = (diff_check.stdout or diff_check.stderr or "").strip()
        return False, f"git diff --check failed: {output[:300]}"

    py_files = [f for f in changed if f.endswith(".py") and (Path(clone_dir) / f).is_file()]
    if py_files:
        compiled = subprocess.run(
            [sys.executable, "-m", "py_compile", *py_files],
            cwd=clone_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if compiled.returncode != 0:
            output = (compiled.stderr or compiled.stdout or "").strip()
            return False, f"py_compile failed: {output[:300]}"
    return True, "git diff --check" + (", py_compile" if py_files else "")


def fix_pipeline_autonomously(
    pr: PullRequest,
    error_logs: str,
    failed_checks: list[str],
    attempt: int,
    max_attempts_value: int,
) -> tuple[bool, str, str]:
    """Attempt one pipeline fix via opencode. Returns (success, message, pushed_sha)."""
    if not error_logs.strip():
        return False, "No pipeline error logs available to act on", ""

    repo = pr.head.repo
    base_repo = pr.base.repo
    if repo.full_name != base_repo.full_name:
        return False, "PR head is a fork — cannot push fixes", ""

    head_branch = pr.head.ref
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    head_clone = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            clone_dir = _setup_clone_environment(tmpdir, head_clone)
            _run_git(["git", "checkout", head_branch], cwd=clone_dir)

            prompt = _build_prompt(error_logs, failed_checks)
            used_model, opencode_error = _run_opencode_fix(clone_dir, prompt)
            if not used_model:
                details = f": {opencode_error}" if opencode_error else ""
                return False, f"opencode did not produce a fix{details}", ""

            changed = _changed_files(clone_dir)
            if not changed:
                return False, "opencode made no file changes", ""

            ok, checks_msg = _validate_changes(clone_dir, changed)
            if not ok:
                return False, checks_msg, ""

            _run_git(["git", "add", "-A"], cwd=clone_dir)
            _run_git(
                [
                    "git",
                    "commit",
                    "-m",
                    f"fix: attempt CI pipeline fix via AI Agent (attempt {attempt}/{max_attempts_value})",
                ],
                cwd=clone_dir,
            )
            _run_git(["git", "push", "origin", head_branch], cwd=clone_dir)
            pushed_sha = _run_git(["git", "rev-parse", "HEAD"], cwd=clone_dir).stdout.strip()

            files_str = ", ".join(f"`{f}`" for f in changed)
            msg = (
                f"Pushed pipeline fix (attempt {attempt}/{max_attempts_value})\n"
                f"**Files:** {files_str}\n"
                f"**Model/Provider:** {used_model}\n"
                f"**Checks:** {checks_msg}"
            )
            return True, msg, pushed_sha

        except subprocess.TimeoutExpired as e:
            return False, f"Pipeline fix timed out: {e.cmd}", ""
        except subprocess.CalledProcessError as e:
            return False, f"Git command failed: {' '.join(e.cmd)} — {(e.stderr or '').strip()}", ""
        except Exception as e:  # noqa: BLE001 - surface any failure as a manual fallback
            return False, f"Error fixing pipeline: {e}", ""
