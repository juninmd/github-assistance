"""On a failing pipeline, attempt an autonomous fix before giving up.

Wraps ``pipeline_fixer`` with bounded attempts tracked by marker comments, so a
green CI can be reached without a human: each attempt pushes a fix commit and the
next CI run validates it. Before editing any file it updates a branch that lags
its base, because failing checks on a stale merge commit are not in the PR code.
Best-effort: never raises into the review run.
"""

from __future__ import annotations

import os
from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant.branch_staleness import commits_behind
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


def update_stale_branch_enabled() -> bool:
    return os.getenv("PIPELINE_FIX_UPDATE_BRANCH", "true").lower() in {"1", "true", "yes", "on"}


def _comment_branch_update(
    pr: PullRequest, github_client: Any, log: Any,
    behind: int, base_ref: str,
) -> None:
    body = (
        "**Pipeline: branch desatualizado**\n\n"
        f"O PR estava **{behind}** commit(s) atrás de `{base_ref}`. O CI valida um merge "
        "desatualizado, que pode falhar sem existir erro no código deste PR — nenhuma "
        "edição de arquivo resolveria.\n\n"
        f"**Ação:** atualizei o branch a partir de `{base_ref}`. O CI vai rodar de novo."
    )
    try:
        github_client.comment_on_pr(pr, body)
    except Exception as e:  # noqa: BLE001
        log(f"Failed to comment branch update on PR #{pr.number}: {e}", "WARNING")


def _try_update_stale_branch(pr: PullRequest, github_client: Any, log: Any) -> bool:
    """Update the PR branch when it lags base; a stale merge commit alone fails CI."""
    if not update_stale_branch_enabled():
        return False
    behind = commits_behind(pr)
    if behind <= 0:
        return False
    base_ref = getattr(pr.base, "ref", "") or "base"
    log(f"PR #{pr.number}: failing on a branch {behind} commit(s) behind {base_ref} — updating")
    try:
        updated, msg, _sha = github_client.update_pr_branch(pr)
    except Exception as e:  # noqa: BLE001 - fall back to the source-edit path
        log(f"update-branch failed on PR #{pr.number}: {e}", "WARNING")
        return False
    if not updated:
        log(f"update-branch rejected on PR #{pr.number}: {msg}", "WARNING")
        return False
    _comment_branch_update(pr, github_client, log, behind, base_ref)
    return True


def attempt_pipeline_fix(pr: PullRequest, github_client: Any, log: Any) -> bool:
    """Try one bounded autonomous pipeline fix. ``True`` when a fix was pushed."""
    if not pipeline_fix_enabled():
        return False
    try:
        status = check_pipeline_status(pr)
        if status["state"] not in ("failure", "error"):
            return False
        if _try_update_stale_branch(pr, github_client, log):
            return True
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
