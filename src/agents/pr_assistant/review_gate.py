"""Draft + check-run gate for critical review findings.

Critical findings (severity ``error``) put the PR in draft and publish an
``action_required`` check so branch protection can block the merge until a new
commit is reviewed and approved. Best-effort: never raises into the agent run.
"""

from __future__ import annotations

import os
from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant.review_verdict import GATE_NAME, LABEL_CRITICAL

_CRITICAL_COLOR = "b60205"


def gate_enabled() -> bool:
    return os.getenv("REVIEW_GATE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def _publish_check(repo: Any, head_sha: str, conclusion: str, summary: str) -> None:
    repo.create_check_run(
        name=GATE_NAME,
        head_sha=head_sha,
        status="completed",
        conclusion=conclusion,
        output={"title": GATE_NAME, "summary": summary},
    )


def _add_critical_label(github_client: Any, pr: PullRequest) -> None:
    repo = pr.base.repo
    existing = {lb.name.lower() for lb in repo.get_labels()}
    if LABEL_CRITICAL.lower() not in existing:
        repo.create_label(name=LABEL_CRITICAL, color=_CRITICAL_COLOR)
    github_client.add_label_to_pr(pr, LABEL_CRITICAL)


def _remove_critical_label(pr: PullRequest) -> None:
    try:
        pr.as_issue().remove_from_labels(LABEL_CRITICAL)
    except Exception:
        return


def apply_gate(
    pr: PullRequest, github_client: Any, verdict: Any, enabled: bool, log: Any
) -> None:
    """Draft + block on critical; publish success and un-draft on approval."""
    if not enabled:
        return
    try:
        repo = pr.base.repo
        if verdict.critical and not verdict.approved:
            _publish_check(
                repo, pr.head.sha, "action_required",
                "Achados críticos encontrados — corrija antes do merge.",
            )
            if not getattr(pr, "draft", False):
                pr.convert_to_draft()
            _add_critical_label(github_client, pr)
        elif verdict.approved:
            _publish_check(repo, pr.head.sha, "success", "Revisão aprovada.")
            if getattr(pr, "draft", False):
                pr.mark_ready_for_review()
            _remove_critical_label(pr)
    except Exception as e:  # noqa: BLE001 - gate must never break the run
        log(f"review gate failed for PR #{getattr(pr, 'number', '?')}: {e}", "WARNING")
