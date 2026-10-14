"""On a failing pipeline, attempt an autonomous fix before giving up.

Wraps ``pipeline_fixer`` with bounded attempts tracked by marker comments, so a
green CI can be reached without a human: each attempt pushes a fix commit and the
next CI run validates it. Best-effort: never raises into the review run.
"""

from __future__ import annotations

from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant.pipeline import check_pipeline_status, get_pipeline_error_logs
from src.agents.pr_assistant.pipeline_fixer import (
    MANUAL_PIPELINE_LABEL,
    build_marker,
    fix_pipeline_autonomously,
    max_attempts,
    pipeline_fix_enabled,
    read_attempt_state,
)


def _comment_attempt(
    pr: PullRequest, github_client: Any, log: Any,
    msg: str, attempt: int, mx: int, sha: str, success: bool,
) -> None:
    author = pr.user.login if pr.user else "contributor"
    outcome = "apliquei uma correção automática no pipeline" if success else (
        "tentei corrigir o pipeline, mas a tentativa falhou"
    )
    body = (
        f"**Tentativa {attempt}/{mx} de corrigir o pipeline**\n\n"
        f"Olá @{author}, {outcome}.\n\n"
        f"**Detalhes:** {msg}\n\n{build_marker(attempt, sha)}"
    )
    try:
        github_client.comment_on_pr(pr, body)
    except Exception as e:  # noqa: BLE001
        log(f"Failed to comment pipeline attempt on PR #{pr.number}: {e}", "WARNING")


def _mark_manual(pr: PullRequest, github_client: Any, log: Any, reason: str) -> None:
    try:
        github_client.add_label_to_pr(pr, MANUAL_PIPELINE_LABEL)
        log(f"PR #{pr.number} marked {MANUAL_PIPELINE_LABEL}: {reason}", "WARNING")
    except Exception as e:  # noqa: BLE001
        log(f"Failed to label PR #{pr.number}: {e}", "WARNING")


def attempt_pipeline_fix(pr: PullRequest, github_client: Any, log: Any) -> bool:
    """Try one bounded autonomous pipeline fix. ``True`` when a fix was pushed."""
    if not pipeline_fix_enabled():
        return False
    try:
        status = check_pipeline_status(pr)
        if status["state"] not in ("failure", "error"):
            return False
        comments = github_client.get_issue_comments(pr)
        last_attempt, _ = read_attempt_state(comments)
        mx = max_attempts()
        if last_attempt >= mx:
            _mark_manual(pr, github_client, log, f"still failing after {last_attempt} attempts")
            return False

        logs_data = get_pipeline_error_logs(pr)
        error_logs = logs_data.get("logs", "")
        failed_checks = logs_data.get("failed_checks", [])
        if not error_logs.strip():
            log(f"No actionable pipeline logs for PR #{pr.number}", "WARNING")
            return False

        attempt = last_attempt + 1
        log(f"PR #{pr.number}: pipeline failing — fix attempt {attempt}/{mx}")
        success, msg, pushed_sha = fix_pipeline_autonomously(
            pr, error_logs, failed_checks, attempt, mx
        )
        _comment_attempt(
            pr, github_client, log, msg, attempt, mx, pushed_sha or pr.head.sha, success
        )
        if success:
            return True
        if attempt >= mx:
            _mark_manual(pr, github_client, log, msg)
        return False
    except Exception as e:  # noqa: BLE001 - advisory, never break the run
        log(f"Pipeline fix attempt failed for PR #{pr.number}: {e}", "WARNING")
        return False
