"""Git-related utility functions for Secret Remover Agent."""
import json
import os
import subprocess
from typing import Any


def _get_remote_url(clone_dir: str) -> str:
    """Read the current origin remote URL before git-filter-repo strips it."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=clone_dir, capture_output=True, text=True, timeout=10,
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
    _token: str,
    log_func: Any,
    default_branch: str = "main",
) -> bool:
    """Write .gitleaks.toml allowlist entries and commit+push directly."""
    toml_path = os.path.join(clone_dir, ".gitleaks.toml")
    existing = ""
    if os.path.exists(toml_path):
        with open(toml_path, encoding="utf-8") as f:
            existing = f.read()

    entry_blocks = []
    for finding in findings:
        description = f"False positive: {finding['rule_id']} in {finding['file']}"
        entry_blocks.append(
            "\n".join([
                "[[allowlist]]",
                f"description = {json.dumps(description)}",
                f"rules = [{json.dumps(finding['rule_id'])}]",
                f"paths = [{json.dumps(finding['file'])}]",
            ])
        )

    new_entries = "\n\n".join(entry_blocks)
    updated_content = (existing.rstrip() + "\n\n" + new_entries).strip() + "\n"

    try:
        with open(toml_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        subprocess.run(
            ["git", "config", "user.email", "secret-remover@github-assistance"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Secret Remover Agent"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "add", ".gitleaks.toml"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"chore: add gitleaks allowlist ({len(findings)} entries)"],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "push", "origin", default_branch],
            cwd=clone_dir, check=True, capture_output=True, text=True,
        )
        log_func(f"Allowlist applied locally for {repo_name} ({len(findings)} entries)")
        return True
    except subprocess.CalledProcessError as exc:
        log_func(f"Failed to apply allowlist for {repo_name}: {exc.stderr}", "WARNING")
        return False


def remove_secret_from_history(
    repo_name: str,
    finding: dict,
    clone_dir: str,
    log_func: Any,
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
            cwd=clone_dir, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log_func(
                f"git-filter-repo failed for {repo_name}/{file_path}: {result.stderr.strip()}",
                "ERROR",
            )
            return False

        # git-filter-repo strips the remote; re-add it for push
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=clone_dir, check=True, capture_output=True, text=True, timeout=10,
        )

        subprocess.run(
            ["git", "push", "--force", "--all"],
            cwd=clone_dir, check=True, capture_output=True, text=True, timeout=120,
        )
        subprocess.run(
            ["git", "push", "--force", "--tags"],
            cwd=clone_dir, capture_output=True, text=True, timeout=120,
        )
        log_func(f"Secret removed from history: {repo_name}/{file_path}")
        return True
    except subprocess.TimeoutExpired:
        log_func(f"Timeout removing secret from {repo_name}/{file_path}", "ERROR")
        return False
    except subprocess.CalledProcessError as exc:
        log_func(f"Error removing secret from {repo_name}/{file_path}: {exc.stderr}", "ERROR")
        return False
