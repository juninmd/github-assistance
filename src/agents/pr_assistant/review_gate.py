"""Draft + commit-status gate for critical review findings.

Critical findings (severity ``error``) put the PR in draft and publish a
``github-assistance/review`` commit status with state ``failure`` so branch
protection can require it: a new commit starts with no status and stays blocked
until the review approves it. Draft itself already blocks a GitHub merge.

Commit statuses (unlike check runs) can be created with a PAT, which is what the
CronJob uses. Best-effort: never raises into the agent run.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant.review_verdict import GATE_NAME, LABEL_CRITICAL

_CRITICAL_COLOR = "b60205"


def gate_enabled() -> bool:
    return os.getenv("REVIEW_GATE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def _best_effort(action: Callable[[], Any], log: Any, what: str) -> None:
    try:
        action()
    except Exception as e:  # noqa: BLE001 - gate must never break the run
        log(f"review gate: {what} failed: {e}", "WARNING")


def _publish_status(repo: Any, head_sha: str, state: str, description: str) -> None:
    repo.get_commit(head_sha).create_status(
        state=state, context=GATE_NAME, description=description
    )


def _add_critical_label(github_client: Any, pr: PullRequest) -> None:
    repo = pr.base.repo
    existing = {lb.name.lower() for lb in repo.get_labels()}
    if LABEL_CRITICAL.lower() not in existing:
        repo.create_label(name=LABEL_CRITICAL, color=_CRITICAL_COLOR)
    github_client.add_label_to_pr(pr, LABEL_CRITICAL)


def _remove_critical_label(pr: PullRequest) -> None:
    pr.as_issue().remove_from_labels(LABEL_CRITICAL)


def apply_gate(
    pr: PullRequest, github_client: Any, verdict: Any, enabled: bool, log: Any
) -> None:
    """Draft + failing status on critical; success and un-draft on approval."""
    if not enabled:
        return
    repo = pr.base.repo
    if verdict.critical and not verdict.approved:
        # Draft first: it is the hard merge block and needs only a PAT GraphQL call.
        if not getattr(pr, "draft", False):
            _best_effort(pr.convert_to_draft, log, "convert_to_draft")
        _best_effort(lambda: _add_critical_label(github_client, pr), log, "label")
        _best_effort(
            lambda: _publish_status(
                repo, pr.head.sha, "failure", "Achados críticos — corrija antes do merge."
            ),
            log,
            "status",
        )
    elif verdict.approved:
        _best_effort(
            lambda: _publish_status(repo, pr.head.sha, "success", "Revisão aprovada."),
            log,
            "status",
        )
        if getattr(pr, "draft", False):
            _best_effort(pr.mark_ready_for_review, log, "mark_ready")
        _best_effort(lambda: _remove_critical_label(pr), log, "unlabel")
