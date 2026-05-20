from __future__ import annotations

import os
import re
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from github.PullRequest import PullRequest

from src.agents.utils import (
    build_authenticated_clone_url,
    get_free_opencode_model,
    setup_git_config,
)
from src.ai import get_ai_client
from src.utils.logger import get_logger

_logger = get_logger("conflict-resolver")

_OPENCODE_DEFAULT_FREE_MODEL = "opencode/big-pickle"
_OPENCODE_MODELS_TIMEOUT = 20
_OPENCODE_RESOLUTION_TIMEOUT = 240


def resolve_conflicts_autonomously(
    pr: PullRequest,
    ai_provider: str = "ollama",
    ai_model: str = "qwen3:1.7b",
    ai_config: dict[str, Any] | None = None,
    allow_ai_fallback: bool | None = None,
) -> tuple[bool, str]:
    provider = os.getenv("CONFLICT_AI_PROVIDER", ai_provider)
    model = os.getenv("CONFLICT_AI_MODEL", ai_model)
    if allow_ai_fallback is None:
        allow_ai_fallback = os.getenv("CONFLICT_AI_FALLBACK_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    config = dict(ai_config or {})
    config["model"] = model
    conflict_client = None
    if allow_ai_fallback:
        with suppress(Exception):
            conflict_client = get_ai_client(provider, **config)

    repo = pr.head.repo
    base_repo = pr.base.repo
    base_branch = pr.base.ref
    head_branch = pr.head.ref

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    head_clone = build_authenticated_clone_url(token, repo.full_name)
    base_clone = build_authenticated_clone_url(token, base_repo.full_name)

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = str(Path(tmpdir) / "repo")
        try:
            _run_git(["git", "clone", "--depth=100", "--no-single-branch", head_clone, clone_dir], cwd=tmpdir)
            setup_git_config(clone_dir)
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
            resolved_files: list[str] = []
            models_used: set[str] = set()
            for filepath in conflicted:
                full_path = Path(clone_dir) / filepath
                if not full_path.exists():
                    continue

                with open(full_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()

                if "<<<<<<< HEAD" not in content:
                    _run_git(["git", "add", filepath], cwd=clone_dir)
                    resolved_count += 1
                    resolved_files.append(filepath)
                    models_used.add("git-auto")
                    continue

                resolved, used_model = _resolve_file_conflicts_with_model(
                    content, conflict_client, provider, model, prefer_opencode=True
                )
                if resolved:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(resolved)
                    _run_git(["git", "add", filepath], cwd=clone_dir)
                    resolved_count += 1
                    resolved_files.append(filepath)
                    models_used.add(used_model)

            if resolved_count == 0:
                return False, "AI could not resolve any conflicts"

            _run_git(
                ["git", "commit", "-m", "fix: resolve merge conflicts via AI Agent"],
                cwd=clone_dir,
            )
            _run_git(["git", "push", "origin", head_branch], cwd=clone_dir)

            files_str = ", ".join(f"`{f}`" for f in resolved_files)
            models_str = ", ".join(sorted(models_used))
            msg = (
                f"Resolved {resolved_count} conflict(s) and pushed\n"
                f"**Files:** {files_str}\n"
                f"**Model/Provider:** {models_str}"
            )
            return True, msg

        except subprocess.TimeoutExpired as e:
            return False, f"Conflict resolution timed out: {e.cmd}"
        except subprocess.CalledProcessError as e:
            return False, f"Git command failed: {' '.join(e.cmd)} \u2014 {(e.stderr or '').strip()}"
        except Exception as e:
            return False, f"Error resolving conflicts: {e}"


def _run_git(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
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
    return get_free_opencode_model(timeout=_OPENCODE_MODELS_TIMEOUT)


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:\w+)?\n(.*?)\n```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _resolve_with_opencode(content: str) -> tuple[str | None, str]:
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
        return None, ""
    if result.returncode != 0 and model != _OPENCODE_DEFAULT_FREE_MODEL:
        model = _OPENCODE_DEFAULT_FREE_MODEL
        try:
            result = subprocess.run(
                ["opencode", "run", "--model", model, prompt],
                capture_output=True,
                text=True,
                timeout=_OPENCODE_RESOLUTION_TIMEOUT,
            )
        except (subprocess.SubprocessError, OSError):
            return None, ""
    if result.returncode != 0:
        return None, ""
    resolved = _strip_markdown_fence(result.stdout or "")
    if not resolved or "<<<<<<< HEAD" in resolved:
        return None, ""
    return resolved, f"opencode/{model}"


def _resolve_file_conflicts_with_model(
    content: str,
    ai_client,
    provider: str,
    model: str,
    prefer_opencode: bool = False,
) -> tuple[str | None, str]:
    if prefer_opencode:
        opencode_resolved, oc_model = _resolve_with_opencode(content)
        if opencode_resolved:
            return opencode_resolved, oc_model
    try:
        if ai_client is None:
            return None, ""
        resolved = ai_client.resolve_conflict(
            file_content=content,
            conflict_block=content,
        )
        if resolved and "<<<<<<< HEAD" not in resolved:
            return resolved, f"{provider}/{model}"
    except Exception as e:
        _logger.error(f"AI conflict resolution error: {e}")
    return None, ""


def _resolve_file_conflicts(content: str, ai_client, prefer_opencode: bool = False) -> str | None:
    resolved, _ = _resolve_file_conflicts_with_model(content, ai_client, "ollama", "unknown", prefer_opencode)
    return resolved
