"""Pipeline status handling for the PR Assistant.

Extracted from ``agent.py`` (Antigravity 150-line guideline): try to auto-fix a
failing pipeline once, warn the author, and otherwise wait/skip.
"""

from __future__ import annotations

from src.agents.pr_assistant.mixins_base import PRAssistantBase
from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    has_existing_failure_comment,
)
from src.agents.pr_assistant.pipeline_fix_flow import attempt_pipeline_fix


class PipelineFlowMixin(PRAssistantBase):
    """Decides whether a PR is blocked by its pipeline checks."""

    def _handle_pipeline_and_skip(
        self, pr, results: dict, issue_comments: list | None = None, status: dict | None = None
    ) -> bool:
        status = status or check_pipeline_status(pr)
        state = status["state"]
        if state in ("failure", "error"):
            # Try to fix the pipeline at least once before just warning the author.
            if attempt_pipeline_fix(pr, self.github_client, self.log):
                self._record_skip(
                    results, pr.number, pr.title, pr.base.repo.full_name,
                    "pipeline_fix_attempted",
                )
                return True
            self._warn_pipeline_failure(pr, status, results, issue_comments)
            self._record_skip(
                results, pr.number, pr.title, pr.base.repo.full_name, "pipeline_failure"
            )
            return True
        if state != "success":
            if status.get("checks", {}).get("total", 0) == 0:
                # No CI checks at all: nothing is pending or failing. Let the merge
                # policy decide (it requires evidence) and still run the review.
                return False
            self._notify_pipeline_pending(pr, state, issue_comments)
            self._record_skip(
                results, pr.number, pr.title, pr.base.repo.full_name, f"pipeline_{state}"
            )
            return True
        return False

    def _warn_pipeline_failure(
        self, pr, status: dict, results: dict, issue_comments: list | None = None
    ) -> None:
        results["pipeline_failures"].append(
            {
                "action": "pipeline_failure",
                "pr": pr.number,
                "title": pr.title,
                "state": status["state"],
                "repository": pr.base.repo.full_name,
            }
        )
        if self.simulation_mode:
            return
        if has_existing_failure_comment(pr, issue_comments):
            return
        comment = build_failure_comment(pr, status.get("failed_checks", []))
        try:
            self.github_client.comment_on_pr(pr, comment)
        except Exception as e:
            self.log(f"Failed to post pipeline-failure comment on PR #{pr.number}: {e}", "WARNING")
