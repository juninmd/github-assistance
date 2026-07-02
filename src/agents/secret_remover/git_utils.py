"""
Git-related utility functions for Secret Remover Agent."""

import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from github import Github

from src.agents import utils as agent_utils


def _build_security_branch(repo_name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", repo_name.lower()).strip("-")
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"agent/security-hardening-for-{slug}-{timestamp}"


def _get_remote_url(clone_dir: str) -> str:
    """Read the current origin remote URL before git-filter-repo strips it."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=clone_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass
    return ""


def apply_allowlist_locally(
    repo_name: str,
    findings: list[dict],
    clone_dir: str,
    token: str,
    log_func: Callable[..., None],
    default_branch: str = "main",
) -> bool:
    """Write .gitleaks.toml allowlist entries, push a branch, and open a PR."""
    toml_path = Path(clone_dir) / ".gitleaks.toml"
    existing = ""
    if toml_path.exists():
        with open(toml_path, encoding="utf-8") as f:
            existing = f.read()

    entry_blocks = []
    for finding in findings:
        description = f"False positive: {finding['rule_id']} in {finding['file']}"
        entry_blocks.append(
            "\n".join(
                [
                    "[[allowlist]]",
                    f"description = {json.dumps(description)}",
                    f"rules = [{json.dumps(finding['rule_id'])}]",
                    f"paths = [{json.dumps(finding['file'])}]",
                ]
            )
        )

    new_entries = "\n\n".join(entry_blocks)
    updated_content = (existing.rstrip() + "\n\n" + new_entries).strip() + "\n"
    branch = _build_security_branch(repo_name)
    title = f"Security hardening for {repo_name}"

    try:
        with open(str(toml_path), "w", encoding="utf-8") as f:
            f.write(updated_content)

        subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "secret-remover@github-assistance"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Secret Remover Agent"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "add", ".gitleaks.toml"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"chore: add gitleaks allowlist ({len(findings)} entries)"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        body = agent_utils.build_pr_body(
            "secret_remover",
            title,
            f"Added {len(findings)} gitleaks allowlist entrie(s).",
            "secret-remover",
        )
        pr = Github(token).get_repo(repo_name).create_pull(
            title=f"[agent/secret_remover] {title}",
            body=body,
            head=branch,
            base=default_branch,
        )
        log_func(f"Allowlist PR opened for {repo_name}: {pr.html_url}")
        return True
    except subprocess.CalledProcessError:
        log_func(f"Failed to apply allowlist for {repo_name}: git command failed", "WARNING")
        return False


def remove_secret_from_history(
    repo_name: str,
    finding: dict,
    clone_dir: str,
    log_func: Callable[..., None],
) -> bool:
    """Run git-filter-repo to purge a file from git history and force-push."""
    file_path = finding.get("file", "")
    if not file_path:
        log_func(f"Cannot remove secret: missing file path for {repo_name}", "ERROR")
        return False

    remote_url = _get_remote_url(clone_dir)
    if not remote_url:
        log_func(f"Cannot remove secret: no remote URL for {repo_name}", "ERROR")
        return False

    try:
        result = subprocess.run(
            ["git-filter-repo", "--path", file_path, "--invert-paths", "--force"],
            cwd=clone_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            log_func(f"git-filter-repo failed for {repo_name}/{file_path}", "ERROR")
            return False

        # git-filter-repo strips the remote; re-add it for push
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        subprocess.run(
            ["git", "push", "--force", "--all"],
            cwd=clone_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "push", "--force", "--tags"],
            cwd=clone_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        log_func(f"Secret removed from history: {repo_name}/{file_path}")
        return True
    except subprocess.TimeoutExpired:
        log_func(f"Timeout removing secret from {repo_name}/{file_path}", "ERROR")
        return False
    except subprocess.CalledProcessError:
        log_func(f"Error removing secret from {repo_name}/{file_path}: git command failed", "ERROR")
        return False
