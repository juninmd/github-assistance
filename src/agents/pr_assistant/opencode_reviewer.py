"""PR code review via the opencode CLI, restricted to free models (zero cost).

Opt-in, independent of the LiteLLM and clawpatch reviewers: reads the PR diff
via the GitHub API (no clone needed) and asks opencode for a findings
summary, falling back across free models the same way pipeline_fixer.py
does for pipeline fixes. Purely advisory — never affects merge_policy.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from github.PullRequest import PullRequest

from src.agents.pr_assistant.conflict_resolver import _get_free_opencode_models, _opencode_cmd
from src.agents.pr_assistant.pr_diff import build_review_prompt, collect_diff
from src.utils.proc import run as proc_run

OPENCODE_REVIEW_MARKER = "<!-- opencode-review -->"
_OPENCODE_REVIEW_TIMEOUT = 180


def opencode_review_enabled() -> bool:
    return os.getenv("OPENCODE_REVIEW_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def has_existing_opencode_review_comment(pr: PullRequest, issue_comments: list | None = None) -> bool:
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        return any(OPENCODE_REVIEW_MARKER in (c.body or "") for c in comments)
    except Exception:
        return False


def _run_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=2048")
    env.setdefault("NODE_ENV", "production")
    return env


def review_pr_with_opencode(pr: PullRequest) -> tuple[bool, str]:
    """Return (success, report_markdown). report is '' when there is nothing to say."""
    diff = collect_diff(pr)
    if not diff.strip():
        return True, ""

    prompt = build_review_prompt(pr, diff)
    env = _run_env()
    last_error = ""
    with tempfile.TemporaryDirectory() as tmpdir:
        for model in _get_free_opencode_models():
            try:
                result = proc_run(
                    [_opencode_cmd(), "run", "--pure", "--model", model, prompt],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_OPENCODE_REVIEW_TIMEOUT,
                    env=env,
                )
                if result.returncode != 0:
                    last_error = f"{model} exited {result.returncode}"
                    continue
                report = (result.stdout or "").strip()
                if not report or report.lower().startswith("no issues found"):
                    return True, ""
                return True, report
            except (subprocess.SubprocessError, OSError) as exc:
                last_error = f"{model} failed to execute: {type(exc).__name__}"
                continue
    return False, last_error or "opencode produced no output"


def build_opencode_review_comment(report: str) -> str:
    if not report:
        return ""
    return "\n".join(
        [
            OPENCODE_REVIEW_MARKER,
            "## 🛠️ Revisão Automática — opencode (modelos gratuitos)\n",
            report,
            "\n---",
            "_Revisão consultiva gerada via opencode (modelo gratuito) por `pr_assistant`; "
            "não afeta a decisão de merge._",
        ]
    )
