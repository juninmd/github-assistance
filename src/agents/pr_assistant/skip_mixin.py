"""PR skipping, no-CI tagging and bot-suggestion helpers for the PR Assistant.

Extracted from ``agent.py`` (Antigravity 150-line guideline). The host agent
provides ``github_client``, ``log`` and the run-level flags used here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.agents.pr_assistant.mixins_base import PRAssistantBase
from src.agents.pr_assistant.pipeline import NO_CI_LABEL, NO_CI_LABEL_COLOR
from src.agents.pr_assistant.utils import is_trusted_author

ALLOWED_AUTHORS = [
    "juninmd",
    "Copilot",
    "Jules da Google",
    "google-labs-jules",
    "google-labs-jules[bot]",
    "gemini-code-assist",
    "gemini-code-assist[bot]",
    "imgbot[bot]",
    "renovate[bot]",
    "dependabot[bot]",
]

BOT_REVIEWS = ["Jules da Google", "google-labs-jules", "gemini-code-assist"]


class SkipMixin(PRAssistantBase):
    """Decides which PRs to skip and applies the no-CI tag / bot suggestions."""

    def _skip_young_pr(self, pr, results: dict, repo_name: str) -> bool:
        if not self._is_pr_old_enough(pr):
            self._record_skip(results, pr.number, pr.title, repo_name, "pr_too_young")
            return True
        return False

    def _skip_labeled_pr(self, pr, results: dict, repo_name: str) -> bool:
        labels = {lb.name for lb in pr.get_labels()}
        if "auto-merge-skip" in labels:
            self._record_skip(results, pr.number, pr.title, repo_name, "auto-merge-skip")
            return True
        return False

    def _skip_untrusted_pr(self, pr, results: dict, repo_name: str) -> bool:
        author = pr.user.login if pr.user else "unknown"
        if not self._is_trusted_author(author):
            self._record_skip(results, pr.number, pr.title, repo_name, "untrusted_author")
            return True
        return False

    def _record_skip(
        self, results: dict, pr_number: int, title: str, repo_name: str, reason: str
    ) -> None:
        results["skipped"].append(
            {
                "pr": pr_number,
                "title": title,
                "reason": reason,
                "repository": repo_name,
            }
        )

    def _tag_no_ci(self, pr) -> None:
        """Label repositórios sem CI para encontrá-los depois e adicionar pipeline."""
        try:
            repo = pr.base.repo
            existing = {lb.name.lower() for lb in repo.get_labels()}
            if NO_CI_LABEL.lower() not in existing:
                repo.create_label(
                    name=NO_CI_LABEL,
                    color=NO_CI_LABEL_COLOR,
                    description="Repositório sem CI configurado",
                )
            self.github_client.add_label_to_pr(pr, NO_CI_LABEL)
        except Exception as e:
            self.log(f"Could not add '{NO_CI_LABEL}' label on PR #{pr.number}: {e}", "WARNING")

    def _is_pr_old_enough(self, pr) -> bool:
        if not pr.created_at:
            return True
        age = datetime.now(UTC) - pr.created_at.replace(tzinfo=UTC)
        return age >= timedelta(minutes=self.min_pr_age_minutes)

    def _is_trusted_author(self, login: str) -> bool:
        return is_trusted_author(login, ALLOWED_AUTHORS)

    def _try_accept_suggestions(self, pr) -> None:
        if self.simulation_mode:
            return
        try:
            _success, _msg, count = self.github_client.accept_review_suggestions(pr, BOT_REVIEWS)
            if count > 0:
                self.log(f"Applied {count} suggestions on PR #{pr.number}")
        except Exception as e:
            self.log(f"Error applying suggestions on PR #{pr.number}: {e}", "WARNING")
