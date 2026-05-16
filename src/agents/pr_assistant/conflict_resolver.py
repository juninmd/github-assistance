"""Autonomous merge conflict resolution for PR Assistant."""
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from github.PullRequest import PullRequest

from src.ai import AIClient, get_ai_client

_OPENCODE_MODEL_CACHE: str | None = None
_DEFAULT_FREE_MODEL = "opencode/big-pickle"
_OPENCODE_MODELS_TIMEOUT = 20
_OPENCODE_RESOLUTION_TIMEOUT = 240


def resolve_conflicts_autonomously(
    pr: PullRequest,
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
    conflict_client = None
    try:
        conflict_client = get_ai_client(provider, **config)
    except Exception:
        pass

    repo = pr.head.repo
    base_repo = pr.base.repo
    base_branch = pr.base.ref
    head_branch = pr.head.ref

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    head_clone = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
    base_clone = f"https://x-access-token:{token}@github.com/{base_repo.full_name}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Clone into a subdirectory to avoid git operating on the tmpdir itself
        clone_dir = str(Path(tmpdir) / "repo")
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
                full_path = Path(clone_dir) / filepath
                if not full_path.exists():
                    continue

                with open(full_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()

                if "<<<<<<< HEAD" not in content:
                    _run_git(["git", "add", filepath], cwd=clone_dir)
                    resolved_count += 1
                    continue

                resolved = _resolve_file_conflicts(content, conflict_client, prefer_opencode=True)
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


def _get_free_opencode_model() -> str:
    global _OPENCODE_MODEL_CACHE
    if _OPENCODE_MODEL_CACHE is not None:
        return _OPENCODE_MODEL_CACHE
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=_OPENCODE_MODELS_TIMEOUT,
        )
        if result.returncode != 0:
            _OPENCODE_MODEL_CACHE = _DEFAULT_FREE_MODEL
            return _OPENCODE_MODEL_CACHE
        models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
        free = [m for m in models if _is_free_model(m)]
        if free:
            _OPENCODE_MODEL_CACHE = sorted(free)[0]
            return _OPENCODE_MODEL_CACHE
    except Exception:
        pass
    _OPENCODE_MODEL_CACHE = _DEFAULT_FREE_MODEL
    return _OPENCODE_MODEL_CACHE


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:\w+)?\n(.*?)\n```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _is_free_model(model: str) -> bool:
    return model.endswith("-free") or model == _DEFAULT_FREE_MODEL


def _resolve_with_opencode(content: str) -> str | None:
    model = _get_free_opencode_model()
    prompt = (
        "You are resolving a git merge conflict. Return ONLY the final full file content "
        "with no markdown fences, no explanations, and no extra text.\n\n"
        "File content with conflict markers:\n"
        f"{content}"
    )
    try:
        result = subprocess.run(
            ["opencode", "run", "--model", model, prompt],
            capture_output=True,
            text=True,
            timeout=_OPENCODE_RESOLUTION_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0 and model != _DEFAULT_FREE_MODEL:
        global _OPENCODE_MODEL_CACHE
        _OPENCODE_MODEL_CACHE = _DEFAULT_FREE_MODEL
        try:
            result = subprocess.run(
                ["opencode", "run", "--model", _DEFAULT_FREE_MODEL, prompt],
                capture_output=True,
                text=True,
                timeout=_OPENCODE_RESOLUTION_TIMEOUT,
            )
        except (subprocess.SubprocessError, OSError):
            return None
    if result.returncode != 0:
        return None
    resolved = _strip_markdown_fence(result.stdout or "")
    if not resolved or "<<<<<<< HEAD" in resolved:
        return None
    return resolved


def _resolve_file_conflicts(content: str, ai_client, prefer_opencode: bool = False) -> str | None:
    """Use AI to resolve conflict markers in a file's content."""
    if prefer_opencode:
        opencode_resolved = _resolve_with_opencode(content)
        if opencode_resolved:
            return opencode_resolved
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
