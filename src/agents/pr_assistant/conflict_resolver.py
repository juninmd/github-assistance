"""Autonomous merge conflict resolution for PR Assistant."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from github.PullRequest import PullRequest

from src.agents import utils as agent_utils
from src.ai import get_ai_client

_OPENCODE_RESOLUTION_TIMEOUT = 240


def _opencode_cmd() -> str:
    return shutil.which("opencode") or "opencode"


def _setup_conflict_client(
    provider: str, model: str, allow_ai_fallback: bool | None, ai_config: dict[str, Any] | None
) -> tuple[str, str, Any | None]:
    """Build AI client for conflict resolution fallback if enabled."""
    resolved_provider = os.getenv("CONFLICT_AI_PROVIDER", provider)
    resolved_model = os.getenv("CONFLICT_AI_MODEL", model)
    if allow_ai_fallback is None:
        allow_ai_fallback = os.getenv("CONFLICT_AI_FALLBACK_ENABLED", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    config = dict(ai_config or {})
    config["model"] = resolved_model
    conflict_client = None
    if allow_ai_fallback:
        try:
            conflict_client = get_ai_client(resolved_provider, **config)
        except Exception:
            pass
    return resolved_provider, resolved_model, conflict_client


def _setup_clone_environment(tmpdir: str, head_clone: str) -> str:
    """Clone repository into tmpdir and configure git."""
    clone_dir = str(Path(tmpdir) / "repo")
    _run_git(
        ["git", "clone", "--depth=100", "--no-single-branch", head_clone, clone_dir], cwd=tmpdir
    )
    _run_git(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        cwd=clone_dir,
    )
    _run_git(["git", "config", "user.name", "github-actions[bot]"], cwd=clone_dir)
    return clone_dir


def _try_merge_base(
    clone_dir: str, base_clone: str, head_branch: str, base_branch: str
) -> tuple[int, str, list[str]]:
    """Attempt merge, retrying with full clone if shallow depth is insufficient."""
    _run_git(["git", "checkout", head_branch], cwd=clone_dir)
    _run_git(["git", "remote", "add", "upstream", base_clone], cwd=clone_dir)
    _run_git(["git", "fetch", "--depth=100", "upstream", base_branch], cwd=clone_dir)

    merge_result = subprocess.run(
        ["git", "merge", f"upstream/{base_branch}"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    merge_stderr = merge_result.stderr.strip()

    if merge_result.returncode == 0:
        return 0, merge_stderr, []

    if (
        "fatal: refusing to merge unrelated histories" in merge_stderr
        or "fatal: no merge base" in merge_stderr
    ):
        _run_git(["git", "fetch", "--unshallow"], cwd=clone_dir)
        merge_result = subprocess.run(
            ["git", "merge", f"upstream/{base_branch}"],
            cwd=clone_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        merge_stderr = merge_result.stderr.strip()
        if (
            merge_result.returncode != 0
            and "fatal: refusing to merge unrelated histories" in merge_stderr
        ):
            return -1, merge_stderr, []
        if merge_result.returncode != 0 and "fatal: no merge base" in merge_stderr:
            return -1, merge_stderr, []

    conflicted = _get_conflicted_files(clone_dir)
    return merge_result.returncode, merge_stderr, conflicted


def _handle_delete_add_conflict(clone_dir: str, filepath: str) -> tuple[bool, str]:
    """Detect delete/add conflicts without resolving them automatically."""
    rc = subprocess.run(["git", "rev-parse", "MERGE_HEAD"], cwd=clone_dir, capture_output=True)
    if rc.returncode != 0:
        return False, ""

    exists_head = (
        subprocess.run(["git", "cat-file", "-e", f"HEAD:{filepath}"], cwd=clone_dir).returncode == 0
    )
    exists_merge = (
        subprocess.run(
            ["git", "cat-file", "-e", f"MERGE_HEAD:{filepath}"], cwd=clone_dir
        ).returncode
        == 0
    )

    if exists_head != exists_merge:
        return False, "manual-delete-add"

    return False, ""


def _resolve_conflicted_file(
    clone_dir: str, filepath: str, conflict_client: Any, provider: str, model: str
) -> tuple[bool, str]:
    """Resolve a single conflicted file. Returns (resolved, used_model)."""
    resolved_del_add, resolved_type = _handle_delete_add_conflict(clone_dir, filepath)
    if resolved_del_add:
        return True, resolved_type

    full_path = Path(clone_dir) / filepath
    if not full_path.exists():
        return False, ""
    with open(full_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    if "<<<<<<< HEAD" not in content:
        _run_git(["git", "add", filepath], cwd=clone_dir)
        return True, "git-auto"
    resolved, used_model = _resolve_file_conflicts_with_model(
        content, conflict_client, provider, model, prefer_opencode=True
    )
    if resolved:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(resolved)
        _run_git(["git", "add", filepath], cwd=clone_dir)
        return True, used_model
    return False, ""


def _commit_and_push_resolution(
    clone_dir: str,
    head_branch: str,
    resolved_files: list[str],
    models_used: set[str],
    resolved_count: int,
    checks_msg: str,
) -> str:
    """Commit and push resolved conflicts."""
    _run_git(["git", "commit", "-m", "fix: resolve merge conflicts via AI Agent"], cwd=clone_dir)
    _run_git(["git", "push", "origin", head_branch], cwd=clone_dir)
    files_str = ", ".join(f"`{f}`" for f in resolved_files)
    models_str = ", ".join(sorted(models_used))
    return (
        f"Resolved {resolved_count} conflict(s) and pushed\n"
        f"**Files:** {files_str}\n"
        f"**Model/Provider:** {models_str}\n"
        f"**Checks:** {checks_msg}"
    )


def _run_post_resolution_checks(clone_dir: str, resolved_files: list[str]) -> tuple[bool, str]:
    """Validate the staged merge result before committing."""
    unresolved = _get_conflicted_files(clone_dir)
    if unresolved:
        files = ", ".join(unresolved)
        return False, f"Unresolved conflict files remain: {files}"

    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--check"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if diff_check.returncode != 0:
        output = (diff_check.stderr or diff_check.stdout or "").strip()
        return False, f"git diff --cached --check failed: {output[:500]}"

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if staged.returncode == 0:
        return False, "No staged conflict-resolution changes to commit"
    if staged.returncode != 1:
        output = (staged.stderr or staged.stdout or "").strip()
        return False, f"Could not inspect staged diff: {output[:500]}"

    checks = ["git diff --cached --check"]
    py_files = [
        file
        for file in resolved_files
        if file.endswith(".py") and (Path(clone_dir) / file).is_file()
    ]
    if py_files:
        py_compile = subprocess.run(
            [sys.executable, "-m", "py_compile", *py_files],
            cwd=clone_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if py_compile.returncode != 0:
            output = (py_compile.stderr or py_compile.stdout or "").strip()
            return False, f"py_compile failed: {output[:500]}"
        checks.append("py_compile")

    return True, ", ".join(checks)


def resolve_conflicts_autonomously(
    pr: PullRequest,
    ai_provider: str = "ollama",
    ai_model: str = "qwen3:1.7b",
    ai_config: dict[str, Any] | None = None,
    allow_ai_fallback: bool | None = None,
) -> tuple[bool, str]:
    """Try to resolve merge conflicts in a PR using OpenCode first.

    AI fallback is opt-in through CONFLICT_AI_FALLBACK_ENABLED=true. This keeps
    conflict handling independent from Ollama outages by default.

    Returns:
        Tuple of (success, message)
    """
    provider = os.getenv("CONFLICT_AI_PROVIDER", ai_provider)
    model = os.getenv("CONFLICT_AI_MODEL", ai_model)
    if allow_ai_fallback is None:
        allow_ai_fallback = os.getenv("CONFLICT_AI_FALLBACK_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    config = dict(ai_config or {})
    config["model"] = model
    conflict_client = None
    if allow_ai_fallback:
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
        try:
            # Use depth=100 to ensure we capture common ancestors between branches.
            # Shallow clones (--depth=1) fail with "unrelated histories" when branches
            # have diverged beyond the shallow history and share no common commit.
            _run_git(["git", "clone", "--depth=100", "--no-single-branch", head_clone, clone_dir], cwd=tmpdir)
            agent_utils.setup_git_config(clone_dir)
            _run_git(["git", "checkout", head_branch], cwd=clone_dir)
            _run_git(["git", "remote", "add", "upstream", base_clone], cwd=clone_dir)
            _run_git(["git", "fetch", "--depth=100", "upstream", base_branch], cwd=clone_dir)

            merge_result = subprocess.run(
                ["git", "merge", f"upstream/{base_branch}"],
                cwd=clone_dir, capture_output=True, text=True, timeout=120,
            )

            if rc == 0:
                return True, "No conflicts found during merge"
            if rc == -1:
                if "refusing to merge unrelated histories" in merge_stderr:
                    return False, f"Branches have truly unrelated histories: {merge_stderr}"
                if "no merge base" in merge_stderr:
                    return False, f"No common merge base: {merge_stderr}"
                return False, f"Merge failed after unshallow: {merge_stderr}"
            if not conflicted:
                return (
                    False,
                    f"Merge failed for unknown reason (no conflicted files detected): {merge_stderr}",
                )

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
                    resolved_count += 1
                    resolved_files.append(filepath)
                    models_used.add(used_model)

            if resolved_count == 0:
                return False, "AI could not resolve any conflicts"

            checks_ok, checks_msg = _run_post_resolution_checks(clone_dir, resolved_files)
            if not checks_ok:
                return False, checks_msg

            files_str = ", ".join(f"`{f}`" for f in resolved_files)
            models_str = ", ".join(sorted(models_used))
            msg = (
                f"Resolved {resolved_count} conflict(s) and pushed\n"
                f"**Files:** {files_str}\n"
                f"**Model/Provider:** {models_str}"
            )
            return True, msg

        except subprocess.TimeoutExpired as e:
            return False, f"Conflict resolution timed out: {_safe_cmd(e.cmd)}"
        except subprocess.CalledProcessError as e:
            return False, f"Git command failed: {_safe_cmd(e.cmd)} — {_redact(e.stderr or '')}"
        except Exception:
            return False, "Error resolving conflicts"


def _redact(text: str) -> str:
    """Remove tokens and secrets from git output before logging or returning."""
    text = re.sub(r"x-access-token:[^@]+@", "x-access-token:REDACTED@", text)
    text = re.sub(r"ghp_[a-zA-Z0-9]{36}", "REDACTED", text)
    text = re.sub(r"ghs_[a-zA-Z0-9]{36}", "REDACTED", text)
    return text.strip()


def _safe_cmd(cmd) -> str:
    if not cmd:
        return ""
    parts = [re.sub(r"x-access-token:[^@]+@", "x-access-token:REDACTED@", str(a)) for a in cmd]
    return " ".join(parts)


def _run_git(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    safe_cmd = [re.sub(r"x-access-token:[^@]+@", "x-access-token:REDACTED@", a) for a in cmd]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    # Merge is expected to fail when there are conflicts — don't raise.
    # Every other git command (clone, checkout, commit, push, ...) must succeed.
    if result.returncode != 0 and "merge" not in cmd:
        raise subprocess.CalledProcessError(
            result.returncode, safe_cmd, result.stdout, _redact(result.stderr or "")
        )
    return result


def _get_conflicted_files(cwd: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    # Support both ```code``` and just raw text
    match = re.search(r"```(?:\w+)?\n(.*?)\n```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _resolve_with_opencode(content: str) -> tuple[str | None, str]:
    """Returns (resolved_content, model_used). model_used is empty string on failure."""
    model = agent_utils._get_cached_free_opencode_model()
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
    if result.returncode != 0 and model != agent_utils._DEFAULT_FREE_MODEL:
        model = agent_utils._DEFAULT_FREE_MODEL
        try:
            result = subprocess.run(
                ["opencode", "run", "--model", model, prompt],
                capture_output=True,
                text=True,
                timeout=_OPENCODE_RESOLUTION_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout:
                # Extract content from the fenced block
                match = re.search(
                    r"CONTENT:\s*\n```(?:\w+)?\n(.*?)\n```", result.stdout, flags=re.DOTALL
                )
                if match:
                    resolved = match.group(1).strip()
                    if resolved and "<<<<<<< HEAD" not in resolved and ">>>>>>>" not in resolved:
                        return resolved, f"opencode/{model}"

                # Fallback to simple strip if format was slightly off
                resolved = _strip_markdown_fence(result.stdout)
                if resolved and "<<<<<<< HEAD" not in resolved and ">>>>>>>" not in resolved:
                    # Clean up the reasoning part if it leaked into the content
                    if "REASONING:" in resolved:
                        resolved = (
                            resolved.split("```")[-2].strip() if "```" in resolved else resolved
                        )
                    return resolved, f"opencode/{model}"

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
    """Returns (resolved_content, model_label). model_label describes what was used."""
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
        print(f"AI conflict resolution error: {e}")
    return None, ""


def _resolve_file_conflicts(content: str, ai_client, prefer_opencode: bool = False) -> str | None:
    resolved, _ = _resolve_file_conflicts_with_model(content, ai_client, "ollama", "unknown", prefer_opencode)
    return resolved
