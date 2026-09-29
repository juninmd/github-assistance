"""Advisory PR code review orchestration: opencode on the cluster LiteLLM.

Primary engine is opencode with the repo cloned and the ``code-review`` skills
loaded; when it cannot run (clone, timeout, OOM) it degrades to a diff-only
LiteLLM call, then to no review. It never raises into the PR Assistant run and
never touches the merge path.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant import review_verdict as rv
from src.agents.pr_assistant import review_workspace as ws
from src.agents.pr_assistant.pr_diff import collect_diff

_MAX_DIFF_CHARS = 12000


def _instructions(pr: PullRequest) -> str:
    return (
        "You are a senior engineer reviewing a pull request. Read the repository in the "
        "current directory and apply the `code-review` skill (plus `security-ops` and "
        "`test-engineering` when relevant). Focus on real defects: bugs, security issues, "
        "and correctness regressions; ignore style nits.\n\n"
        "Respond with ONLY one JSON object, no prose and no markdown fences:\n"
        '{"verdict":"APPROVE|REQUEST_CHANGES","summary":"short PT-BR summary",'
        '"findings":[{"file":"path","line":0,"severity":"error|warn|nit","issue":"..."}]}\n'
        "Use APPROVE when there is no blocking problem.\n\n"
        f"PR title: {pr.title}\n"
    )


def _json_prompt(pr: PullRequest, diff: str) -> str:
    body = diff or collect_diff(pr)
    return f"{_instructions(pr)}\nDiff:\n{body}"


def _fallback_verdict(pr: PullRequest, ai_client: Any | None) -> rv.ReviewVerdict | None:
    if ai_client is None:
        return None
    try:
        text = ai_client.generate(_json_prompt(pr, ""))
    except Exception:
        return None
    return rv.parse_review(text, model="cloud/auto (litellm)")


def _via_opencode(pr: PullRequest, token: str, model: str) -> str | None:
    """Clone, run opencode, and return its stdout (``None`` on any failure)."""
    try:
        with tempfile.TemporaryDirectory(prefix=ws.REVIEW_PREFIX) as tmpdir:
            try:
                clone_dir = ws.clone_pr_head(pr, tmpdir, token)
                ws.write_opencode_config(clone_dir)
                prompt = _json_prompt(pr, ws.local_diff(clone_dir, pr.base.ref, _MAX_DIFF_CHARS))
                return ws.run_opencode(clone_dir, prompt, model, ws.review_timeout())
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        return None


def run_review(pr: PullRequest, ai_client: Any | None = None) -> rv.ReviewVerdict | None:
    """Return a review verdict, or ``None`` when the review could not run."""
    ws.cleanup_stale_review_dirs()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    model = ws.review_model()
    output = _via_opencode(pr, token, model) if token else None
    verdict = rv.parse_review(output, model=model) if output else None
    return verdict or _fallback_verdict(pr, ai_client)
