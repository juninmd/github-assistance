"""Secure git operations that avoid embedding tokens in clone URLs.

Uses GIT_ASKPASS to provide credentials without exposing them on the command line.
"""
import os
import subprocess
import tempfile
from typing import Any


def configure_git_auth(token: str | None = None) -> None:
    """Write a temporary GIT_ASKPASS script and set GIT_ASKPASS env var.

    The script outputs the token when git prompts for a password.
    Safe to call multiple times (creates a fresh script each call).
    """
    t = token or os.getenv("GITHUB_TOKEN", "")
    if not t:
        return
    fd, path = tempfile.mkstemp(prefix="git-askpass-", suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write("#!/bin/sh\n")
        f.write('case "$1" in\n')
        f.write('  Username*) echo "x-access-token" ;;\n')
        f.write('  Password*) echo "' + t + '" ;;\n')
        f.write('  *) exit 1 ;;\n')
        f.write("esac\n")
    os.chmod(path, 0o500)
    os.environ["GIT_ASKPASS"] = path
    os.environ["GIT_TERMINAL_PROMPT"] = "0"


def clone_repo_securely(
    repo_name: str,
    clone_dir: str,
    token: str | None = None,
    single_branch: bool = True,
    depth: int | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess:
    """Clone a repository using GIT_ASKPASS to avoid URL-embedded tokens."""
    configure_git_auth(token)
    cmd = ["git", "clone"]
    if single_branch:
        cmd.append("--single-branch")
    if depth:
        cmd.extend(["--depth", str(depth)])
    cmd.extend([f"https://github.com/{repo_name}.git", clone_dir])
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )


def run_git_with_token(
    args: list[str],
    token: str | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Run a git command with GIT_ASKPASS configured for token auth."""
    configure_git_auth(token)
    return subprocess.run(args, **kwargs)
