"""Commit and push review fixes back to the PR head branch (best-effort).

Returns ``(False, "")`` on any failure so a review-fix can never raise into the
PR Assistant run.
"""

from __future__ import annotations

import subprocess

from src.utils.proc import run as proc_run

_GIT_TIMEOUT = 120


def _git(args: list[str], cwd: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    return proc_run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def commit_and_push(clone_dir: str, head_ref: str, message: str) -> tuple[bool, str]:
    """Stage everything, commit and push to ``head_ref``; return ``(ok, sha)``."""
    try:
        _git(["add", "-A"], clone_dir, timeout=60)
        # Never commit our own opencode provider config, even if the model writes one.
        _git(["rm", "--cached", "--ignore-unmatch", "opencode.json"], clone_dir, timeout=30)
        staged = _git(["diff", "--cached", "--quiet"], clone_dir, timeout=30)
        if staged.returncode != 1:  # 0 = nothing staged, other = error
            return False, ""
        commit = _git(
            [
                "-c", "user.email=github-assistance@github.com",
                "-c", "user.name=github-assistance",
                "commit", "-m", message,
            ],
            clone_dir, timeout=60,
        )
        if commit.returncode != 0:
            return False, ""
        push = _git(["push", "origin", f"HEAD:{head_ref}"], clone_dir)
        if push.returncode != 0:
            return False, ""
        sha = _git(["rev-parse", "HEAD"], clone_dir, timeout=30).stdout.strip()
        return True, sha
    except (subprocess.SubprocessError, OSError):
        return False, ""
