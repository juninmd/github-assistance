"""Autonomous merge conflict resolution for PR Assistant."""
import os
import subprocess
import tempfile
from typing import Any

from src.ai import AIClient, get_ai_client


def resolve_conflicts_autonomously(
    pr,
    ai_provider: str = "ollama",
    ai_model: str = "qwen3:1.7b",
    ai_config: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Try to resolve merge conflicts in a PR using AI.

    Supports CONFLICT_AI_PROVIDER and CONFLICT_AI_MODEL env var overrides
    for using a more powerful model specifically for conflict resolution.

    Returns:
        Tuple of (success, message)
    """
    provider = os.getenv("CONFLICT_AI_PROVIDER", ai_provider)
    model = os.getenv("CONFLICT_AI_MODEL", ai_model)
    config = dict(ai_config or {})
    config["model"] = model
    conflict_client = get_ai_client(provider, **config)

    repo = pr.head.repo
    base_repo = pr.base.repo
    base_branch = pr.base.ref
    head_branch = pr.head.ref

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    head_clone = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
    base_clone = f"https://x-access-token:{token}@github.com/{base_repo.full_name}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Clone into a subdirectory to avoid git operating on the tmpdir itself
        clone_dir = os.path.join(tmpdir, "repo")
        try:
            # Use depth=100 to ensure we capture common ancestors between branches.
            # Shallow clones (--depth=1) fail with "unrelated histories" when branches
            # have diverged beyond the shallow history and share no common commit.
            _run_git(["git", "clone", "--depth=100", "--no-single-branch", head_clone, clone_dir], cwd=tmpdir)
            _run_git(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], cwd=clone_dir)
            _run_git(["git", "config", "user.name", "github-actions[bot]"], cwd=clone_dir)
            _run_git(["git", "checkout", head_branch], cwd=clone_dir)
            _run_git(["git", "remote", "add", "upstream", base_clone], cwd=clone_dir)
            _run_git(["git", "fetch", "--depth=100", "upstream", base_branch], cwd=clone_dir)

            merge_result = subprocess.run(
                ["git", "merge", f"upstream/{base_branch}"],
                cwd=clone_dir, capture_output=True, text=True, timeout=120,
            )

            merge_stderr = merge_result.stderr.strip()

            if merge_result.returncode == 0:
                return True, "No conflicts found during merge"

            if "fatal: refusing to merge unrelated histories" in merge_stderr or "fatal: no merge base" in merge_stderr:
                # depth=100 was too shallow — convert to full clone and retry
                _run_git(["git", "fetch", "--unshallow"], cwd=clone_dir)
                merge_result = subprocess.run(
                    ["git", "merge", f"upstream/{base_branch}"],
                    cwd=clone_dir, capture_output=True, text=True, timeout=300,
                )
                merge_stderr = merge_result.stderr.strip()
                if merge_result.returncode != 0 and "fatal: refusing to merge unrelated histories" in merge_stderr:
                    return False, f"Branches have truly unrelated histories: {merge_stderr}"
                if merge_result.returncode != 0 and "fatal: no merge base" in merge_stderr:
                    return False, f"No common merge base: {merge_stderr}"
                if merge_result.returncode != 0:
                    conflicted = _get_conflicted_files(clone_dir)
                    if not conflicted:
                        return False, f"Merge failed after unshallow: {merge_stderr}"

            conflicted = _get_conflicted_files(clone_dir)
            if not conflicted:
                return False, f"Merge failed for unknown reason (no conflicted files detected): {merge_stderr}"

            resolved_count = 0
            for filepath in conflicted:
                full_path = os.path.join(clone_dir, filepath)
                if not os.path.exists(full_path):
                    continue

                with open(full_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()

                if "<<<<<<< HEAD" not in content:
                    _run_git(["git", "add", filepath], cwd=clone_dir)
                    resolved_count += 1
                    continue

                resolved = _resolve_file_conflicts(content, conflict_client)
                if resolved:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(resolved)
                    _run_git(["git", "add", filepath], cwd=clone_dir)
                    resolved_count += 1

            if resolved_count == 0:
                return False, "AI could not resolve any conflicts"

            _run_git(
                ["git", "commit", "-m", "fix: resolve merge conflicts via AI Agent"],
                cwd=clone_dir,
            )
            _run_git(["git", "push", "origin", head_branch], cwd=clone_dir)

            return True, f"Resolved {resolved_count} conflict(s) and pushed"

        except subprocess.TimeoutExpired as e:
            return False, f"Conflict resolution timed out: {e.cmd}"
        except subprocess.CalledProcessError as e:
            return False, f"Git command failed: {' '.join(e.cmd)} — {(e.stderr or '').strip()}"
        except Exception as e:
            return False, f"Error resolving conflicts: {e}"


def _run_git(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    # Merge is expected to fail when there are conflicts — don't raise.
    # Every other git command (clone, checkout, commit, push, ...) must succeed.
    if result.returncode != 0 and "merge" not in cmd:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )
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
        # Pass full content as both file_content and conflict_block so the model
        # has all the context needed to return a clean, fully resolved file.
        resolved = ai_client.resolve_conflict(
            file_content=content,
            conflict_block=content,
        )
        if resolved and "<<<<<<< HEAD" not in resolved:
            return resolved
    except Exception as e:
        print(f"AI conflict resolution error: {e}")
    return None
