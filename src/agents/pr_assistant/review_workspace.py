"""Ephemeral clone + opencode execution for the advisory PR code review.

Disk safety: the clone is shallow (one commit, single branch), lives under a
``pr-review-*`` temp dir, is always removed, and stale dirs from a killed run
are swept on entry.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from github.PullRequest import PullRequest

from src.utils.proc import run as proc_run

DEFAULT_MODEL = "litellm/cloud/auto"
CLONE_TIMEOUT = 120
STALE_AGE_SECONDS = 7200
REVIEW_PREFIX = "pr-review-"
DEFAULT_TIMEOUT = 300


def opencode_cmd() -> str:
    return shutil.which("opencode") or "opencode"


def review_timeout() -> int:
    try:
        return int(os.getenv("OPENCODE_REVIEW_TIMEOUT", "") or DEFAULT_TIMEOUT)
    except ValueError:
        return DEFAULT_TIMEOUT


def review_model() -> str:
    return os.getenv("OPENCODE_REVIEW_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def litellm_base() -> str:
    base = os.getenv("LITELLM_API_BASE", "http://litellm.ai.svc.cluster.local:4000").rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def cleanup_stale_review_dirs(root: str = tempfile.gettempdir()) -> None:
    """Remove leftover clones from a crashed/timed-out prior run."""
    now = time.time()
    for path in Path(root).glob(f"{REVIEW_PREFIX}*"):
        try:
            if path.is_dir() and now - path.stat().st_mtime > STALE_AGE_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def clone_pr_head(pr: PullRequest, tmpdir: str, token: str) -> str:
    """Shallow-clone the PR head branch; raise when the clone fails."""
    head = pr.head
    url = f"https://x-access-token:{token}@github.com/{head.repo.full_name}.git"
    dest = str(Path(tmpdir) / "repo")
    clone = proc_run(
        ["git", "clone", "--depth=1", "--single-branch", "--branch", head.ref, url, dest],
        capture_output=True, text=True, timeout=CLONE_TIMEOUT,
    )
    if clone.returncode != 0:
        raise RuntimeError("review clone failed")
    proc_run(["git", "fetch", "--depth=1", "origin", pr.base.ref], cwd=dest, capture_output=True)
    return dest


def local_diff(clone_dir: str, base_ref: str, max_chars: int) -> str:
    res = proc_run(
        ["git", "diff", "--unified=3", f"origin/{base_ref}", "HEAD"],
        cwd=clone_dir, capture_output=True, text=True, timeout=60,
    )
    return (res.stdout or "")[:max_chars]


def write_opencode_config(config_dir: str) -> None:
    """Point an opencode config dir at the cluster LiteLLM proxy.

    Written to a *config* directory outside the PR clone so it is never staged
    or committed by the auto-fix.
    """
    config = (
        "{\n"
        '  "$schema": "https://opencode.ai/config.json",\n'
        '  "provider": { "litellm": {\n'
        '    "npm": "@ai-sdk/openai-compatible",\n'
        '    "name": "LiteLLM",\n'
        '    "options": { "baseURL": "' + litellm_base() + '", "apiKey": "{env:LITELLM_API_KEY}" },\n'
        '    "models": { "cloud/auto": { "name": "cloud/auto" } }\n'
        "  } }\n"
        "}\n"
    )
    target = Path(config_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "opencode.json").write_text(config, encoding="utf-8")


def run_opencode(clone_dir: str, prompt: str, model: str, timeout: int) -> str | None:
    """Run opencode non-interactively with bounded Node heap; None on any failure."""
    env = os.environ.copy()
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=1536")
    env.setdefault("NODE_ENV", "production")
    try:
        result = proc_run(
            [opencode_cmd(), "run", "--pure", "--model", model, prompt],
            cwd=clone_dir, capture_output=True, text=True, timeout=timeout, env=env,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout if result.returncode == 0 else None
