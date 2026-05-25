"""Autonomous merge conflict resolution for PR Assistant."""
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from github.PullRequest import PullRequest

from src.ai import get_ai_client

_OPENCODE_MODEL_CACHE: str | None = None
_DEFAULT_FREE_MODEL = "opencode/big-pickle"
_OPENCODE_MODELS_TIMEOUT = 20
_OPENCODE_RESOLUTION_TIMEOUT = 240


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
            return False, f"Git command failed: {' '.join(e.cmd)} — {(e.stderr or '').strip()}"
        except Exception as e:
            return False, f"Error resolving conflicts: {e}"


def _run_git(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    # Redact token from command for logging
    safe_cmd = []
    for arg in cmd:
        if "x-access-token:" in arg:
            safe_cmd.append(re.sub(r"x-access-token:[^@]+@", "x-access-token:REDACTED@", arg))
        else:
            safe_cmd.append(arg)
            
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    # Merge is expected to fail when there are conflicts — don't raise.
    # Every other git command (clone, checkout, commit, push, ...) must succeed.
    if result.returncode != 0 and "merge" not in cmd:
        stderr = result.stderr or ""
        # Redact token from stderr too
        safe_stderr = re.sub(r"ghp_[a-zA-Z0-9]{36}", "ghp_REDACTED", stderr)
        raise subprocess.CalledProcessError(
            result.returncode, safe_cmd, result.stdout, safe_stderr
        )
    return result


def _get_conflicted_files(cwd: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=cwd, capture_output=True, text=True, timeout=30,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def _get_free_opencode_models() -> list[str]:
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=_OPENCODE_MODELS_TIMEOUT,
        )
        if result.returncode != 0:
            return [_DEFAULT_FREE_MODEL]
        models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
        free = [m for m in models if _is_free_model(m)]
        # Sort to put preferred models first (e.g. deepseek)
        return sorted(free, key=lambda m: 0 if "deepseek" in m else 1) if free else [_DEFAULT_FREE_MODEL]
    except Exception:
        return [_DEFAULT_FREE_MODEL]


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    # Support both ```code``` and just raw text
    match = re.search(r"```(?:\w+)?\n(.*?)\n```", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _is_free_model(model: str) -> bool:
    return model.endswith("-free") or model == _DEFAULT_FREE_MODEL


def _resolve_with_opencode(content: str) -> tuple[str | None, str]:
    """Returns (resolved_content, model_used). model_used is empty string on failure."""
    models = _get_free_opencode_models()
    
    # Using a more sophisticated prompt to help the model reason through the conflict
    prompt_template = (
        "You are an expert software engineer resolving a git merge conflict.\n"
        "Analyze the following file content which contains conflict markers (<<<<<<< HEAD, =======, >>>>>>>).\n"
        "1. Identify the changes in HEAD (current branch) and the changes in the incoming branch.\n"
        "2. Resolve the conflict by combining the logic correctly, maintaining code integrity and style.\n"
        "3. Provide the full resolved file content.\n\n"
        "Output format:\n"
        "REASONING: <your brief explanation of how you resolved it>\n"
        "CONTENT: \n"
        "```\n"
        "<full resolved file content here>\n"
        "```\n\n"
        "File content with conflicts:\n"
        f"{content}"
    )

    for model in models:
        try:
            result = subprocess.run(
                ["opencode", "run", "--model", model, prompt_template],
                capture_output=True,
                text=True,
                timeout=_OPENCODE_RESOLUTION_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout:
                # Extract content from the fenced block
                match = re.search(r"CONTENT:\s*\n```(?:\w+)?\n(.*?)\n```", result.stdout, flags=re.DOTALL)
                if match:
                    resolved = match.group(1).strip()
                    if resolved and "<<<<<<< HEAD" not in resolved and ">>>>>>>" not in resolved:
                        return resolved, f"opencode/{model}"
                
                # Fallback to simple strip if format was slightly off
                resolved = _strip_markdown_fence(result.stdout)
                if resolved and "<<<<<<< HEAD" not in resolved and ">>>>>>>" not in resolved:
                    # Clean up the reasoning part if it leaked into the content
                    if "REASONING:" in resolved:
                         resolved = resolved.split("```")[-2].strip() if "```" in resolved else resolved
                    return resolved, f"opencode/{model}"
                    
        except (subprocess.SubprocessError, OSError):
            continue
            
    return None, ""


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
