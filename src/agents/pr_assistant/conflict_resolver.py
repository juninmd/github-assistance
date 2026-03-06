"""Autonomous merge conflict resolution for PR Assistant."""
import os
import subprocess
import tempfile
from typing import Any

from src.ai_client import get_ai_client


def resolve_conflicts_autonomously(
    pr,
    ai_provider: str = "ollama",
    ai_model: str = "qwen3:1.7b",
    ai_config: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Try to resolve merge conflicts in a PR using AI.

    Returns:
        Tuple of (success, message)
    """
    config = ai_config or {}
    config["model"] = ai_model
    conflict_client = get_ai_client(ai_provider, **config)

    repo = pr.head.repo
    base_repo = pr.base.repo
    base_branch = pr.base.ref
    head_branch = pr.head.ref

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    head_clone = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
    base_clone = f"https://x-access-token:{token}@github.com/{base_repo.full_name}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            _run_git(["git", "clone", head_clone, tmpdir], cwd=tmpdir)
            _run_git(["git", "checkout", head_branch], cwd=tmpdir)
            _run_git(["git", "remote", "add", "upstream", base_clone], cwd=tmpdir)
            _run_git(["git", "fetch", "upstream", base_branch], cwd=tmpdir)

            merge_result = subprocess.run(
                ["git", "merge", f"upstream/{base_branch}"],
                cwd=tmpdir, capture_output=True, text=True, timeout=120,
            )

            if merge_result.returncode == 0:
                return True, "No conflicts found during merge"

            conflicted = _get_conflicted_files(tmpdir)
            if not conflicted:
                return False, "Merge failed but no conflicted files detected"

            resolved_count = 0
            for filepath in conflicted:
                full_path = os.path.join(tmpdir, filepath)
                if not os.path.exists(full_path):
                    continue

                with open(full_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()

                if "<<<<<<< HEAD" not in content:
                    _run_git(["git", "add", filepath], cwd=tmpdir)
                    resolved_count += 1
                    continue

                resolved = _resolve_file_conflicts(content, conflict_client)
                if resolved:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(resolved)
                    _run_git(["git", "add", filepath], cwd=tmpdir)
                    resolved_count += 1

            if resolved_count == 0:
                return False, "AI could not resolve any conflicts"

            _run_git(
                ["git", "commit", "-m", "fix: resolve merge conflicts via AI Agent"],
                cwd=tmpdir,
            )
            _run_git(["git", "push", "origin", head_branch], cwd=tmpdir)

            return True, f"Resolved {resolved_count} conflict(s) and pushed"

        except subprocess.TimeoutExpired:
            return False, "Conflict resolution timed out"
        except Exception as e:
            return False, f"Error resolving conflicts: {e}"


def _run_git(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 and "merge" not in " ".join(cmd):
        print(f"Git command failed: {' '.join(cmd)} — {result.stderr.strip()}")
    return result


def _get_conflicted_files(cwd: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=cwd, capture_output=True, text=True, timeout=30,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def _resolve_file_conflicts(content: str, ai_client) -> str | None:
    """Use AI to resolve conflict markers in a file's content."""
    try:
        resolved = ai_client.resolve_conflict(content)
        if resolved and "<<<<<<< HEAD" not in resolved:
            return resolved
    except Exception as e:
        print(f"AI conflict resolution error: {e}")
    return None
