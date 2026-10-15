"""Comment/notification helpers for the PR Assistant.

Extracted from ``agent.py`` (Antigravity 150-line guideline). Every method here
is best-effort: notifications must never break the merge workflow.
"""

from __future__ import annotations

from src.agents.pr_assistant.mixins_base import PRAssistantBase
from src.agents.pr_assistant.notifications import (
    notify_conflicts,
    notify_merge_failed,
    notify_merged,
    notify_pipeline_pending,
)


class NotifyMixin(PRAssistantBase):
    """Thin, simulation-aware wrappers around the notification helpers."""

    def _handle_conflicts(self, pr, results: dict, issue_comments: list | None = None) -> None:
        results["skipped"].append(
            {
                "pr": pr.number,
                "title": pr.title,
                "reason": "has_conflicts",
                "repository": pr.base.repo.full_name,
            }
        )
        if not self.simulation_mode:
            self._notify_conflicts(pr, issue_comments)

    def _notify_conflict_resolved(self, pr, msg: str) -> None:
        from src.agents.pr_assistant.notifications import notify_conflict_resolved

        notify_conflict_resolved(self.github_client, self.telegram, pr, msg)

    def _notify_conflicts(self, pr, issue_comments: list | None = None) -> None:
        if self.simulation_mode:
            return
        notify_conflicts(self.github_client, self.telegram, pr, issue_comments)

    def _notify_merged(self, pr, issue_comments: list | None = None) -> None:
        if self.simulation_mode:
            return
        notify_merged(self.github_client, pr, issue_comments)

    def _notify_merge_failed(self, pr, error: str, issue_comments: list | None = None) -> None:
        if self.simulation_mode:
            return
        notify_merge_failed(self.github_client, self.telegram, pr, error, issue_comments)

    def _notify_pipeline_pending(self, pr, state: str, issue_comments: list | None = None) -> None:
        if self.simulation_mode:
            return
        notify_pipeline_pending(self.github_client, self.telegram, pr, state, issue_comments)
