"""
PR Assistant Agent - Auto-merges PRs, resolves conflicts, and manages pipelines.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant.conflict_resolver import resolve_conflicts_autonomously
from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    has_existing_failure_comment,
)
from src.agents.pr_assistant.telegram_summary import build_and_send_summary
from src.ai_client import get_ai_client


class PRAssistantAgent(BaseAgent):
    """Monitors and processes PRs across all repositories."""

    ALLOWED_AUTHORS = [
        "juninmd", "Copilot", "Jules da Google",
        "google-labs-jules", "google-labs-jules[bot]",
        "gemini-code-assist", "gemini-code-assist[bot]",
        "imgbot[bot]", "renovate[bot]", "dependabot[bot]",
    ]

    BOT_REVIEW_USERNAMES = [
        "Jules da Google", "google-labs-jules",
        "google-labs-jules[bot]", "gemini-code-assist",
        "gemini-code-assist[bot]",
    ]

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str = "gemini",
        ai_model: str = "gemini-2.5-flash",
        ai_config: dict[str, Any] | None = None,
        target_owner: str = "juninmd",
        min_pr_age_minutes: int = 10,
        pr_ref: str | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="pr_assistant", **kwargs)
        self.target_owner = target_owner
        self.min_pr_age_minutes = min_pr_age_minutes
        self.pr_ref = pr_ref
        ai_config = ai_config or {}
        ai_config["model"] = ai_model
        self.ai_client = get_ai_client(ai_provider, **ai_config)
        self.ai_provider = ai_provider
        self.ai_model = ai_model
        self.ai_config = ai_config

    def run(self) -> dict[str, Any]:
        """Execute the PR assistant workflow."""
        self.log("Starting PR Assistant workflow")
        results: dict[str, list] = {
            "merged": [], "conflicts_resolved": [],
            "pipeline_failures": [], "skipped": [],
            "timestamp": datetime.now().isoformat(),
        }

        prs = self._get_prs_to_process()
        for pr in prs:
            try:
                self._process_pr(pr, results)
            except Exception as e:
                self.log(f"Error processing PR #{pr.number}: {e}", "ERROR")
                results["skipped"].append({"pr": pr.number, "reason": "error", "error": str(e)})

        build_and_send_summary(results, self.telegram, self.target_owner)
        return results

    def _get_prs_to_process(self) -> list:
        """Get PRs to process — either a specific ref or all open PRs."""
        if self.pr_ref:
            return self._get_pr_from_ref(self.pr_ref)

        query = f"is:pr is:open archived:false user:{self.target_owner}"
        issues = self.github_client.search_prs(query)
        prs = []
        for issue in issues:
            try:
                prs.append(self.github_client.get_pr_from_issue(issue))
            except Exception as e:
                self.log(f"Error fetching PR: {e}", "WARNING")
        return prs

    def _get_pr_from_ref(self, ref: str) -> list:
        """Parse 'owner/repo#number' and return the PR."""
        try:
            repo_ref, pr_number = ref.rsplit("#", 1)
            repo = self.github_client.get_repo(repo_ref)
            return [repo.get_pull(int(pr_number))]
        except Exception as e:
            self.log(f"Error fetching PR from ref '{ref}': {e}", "ERROR")
            return []

    def _process_pr(self, pr, results: dict) -> None:
        """Process a single PR through the full pipeline."""
        repo_name = pr.base.repo.full_name
        self.log(f"Processing PR #{pr.number} in {repo_name}")

        # 0. Check PR age
        if not self._is_pr_old_enough(pr):
            return

        # 1. Check author
        author = pr.user.login if pr.user else "unknown"
        if not self._is_trusted_author(author):
            self.log(f"Skipping PR #{pr.number} from untrusted author: {author}")
            results["skipped"].append({"pr": pr.number, "reason": "untrusted_author", "author": author, "repository": repo_name})
            return

        # 2. Accept review suggestions from bots
        self._try_accept_suggestions(pr)

        # 3. Check mergeability
        if pr.mergeable is None:
            self.log(f"PR #{pr.number} mergeability unknown — skipping")
            results["skipped"].append({"pr": pr.number, "reason": "mergeable_unknown", "repository": repo_name})
            return

        if not pr.mergeable:
            self._handle_conflicts(pr, results)
            return

        # 4. Check pipeline
        status = check_pipeline_status(pr)
        state = status["state"]

        if state == "success":
            self._try_merge(pr, results)
        elif state in ("failure", "error"):
            self._handle_pipeline_failure(pr, status, results)
        else:
            self.log(f"PR #{pr.number} pipeline is '{state}' — skipping")
            results["skipped"].append({"pr": pr.number, "reason": f"pipeline_{state}", "repository": repo_name})

    def _is_pr_old_enough(self, pr) -> bool:
        """Check if PR meets the minimum age requirement."""
        if not pr.created_at:
            return True
        age = datetime.now(UTC) - pr.created_at.replace(tzinfo=UTC)
        if age < timedelta(minutes=self.min_pr_age_minutes):
            minutes = int(age.total_seconds() / 60)
            self.log(f"PR #{pr.number} is too young ({minutes}m, min {self.min_pr_age_minutes}m)")
            return False
        return True

    def _is_trusted_author(self, author: str) -> bool:
        normalized = [a.lower().replace("[bot]", "") for a in self.ALLOWED_AUTHORS]
        return author.lower().replace("[bot]", "") in normalized

    def _try_accept_suggestions(self, pr) -> None:
        """Try to accept review suggestions from bots."""
        try:
            success, msg, count = self.github_client.accept_review_suggestions(pr, self.BOT_REVIEW_USERNAMES)
            if count > 0:
                self.log(f"Applied {count} suggestion(s) on PR #{pr.number}")
            elif not success:
                self.log(f"Error applying suggestions on PR #{pr.number}: {msg}", "WARNING")
        except Exception as e:
            self.log(f"Error applying suggestions on PR #{pr.number}: {e}", "WARNING")

    def _handle_conflicts(self, pr, results: dict) -> None:
        """Handle merge conflicts — try autonomous resolution."""
        self.log(f"PR #{pr.number} has conflicts — attempting autonomous resolution")
        success, msg = resolve_conflicts_autonomously(
            pr, ai_provider=self.ai_provider, ai_model=self.ai_model, ai_config=self.ai_config,
        )
        if success:
            self.log(f"Conflicts resolved for PR #{pr.number}: {msg}")
            results["conflicts_resolved"].append({"pr": pr.number, "repository": pr.base.repo.full_name, "message": msg})
        else:
            self.log(f"Could not resolve conflicts for PR #{pr.number}: {msg}", "WARNING")
            self._notify_conflicts(pr)
            results["skipped"].append({"pr": pr.number, "reason": "unresolved_conflicts", "repository": pr.base.repo.full_name})

    def _notify_conflicts(self, pr) -> None:
        """Post a comment about unresolved conflicts (if not already posted)."""
        try:
            for comment in pr.get_issue_comments():
                if "Conflitos de Merge Detectados" in (comment.body or ""):
                    return
            author = pr.user.login if pr.user else "contributor"
            self.github_client.comment_on_pr(pr, (
                f"⚠️ **Conflitos de Merge Detectados**\n\n"
                f"Olá @{author}, existem conflitos que impedem o merge automático.\n"
                f"Por favor, resolva os conflitos localmente ou via interface do GitHub."
            ))
        except Exception as e:
            self.log(f"Error notifying conflicts on PR #{pr.number}: {e}", "WARNING")

    def _try_merge(self, pr, results: dict) -> None:
        """Attempt to merge the PR."""
        success, msg = self.github_client.merge_pr(pr)
        repo_name = pr.base.repo.full_name
        if success:
            self.log(f"PR #{pr.number} merged successfully")
            results["merged"].append({"action": "merged", "pr": pr.number, "title": pr.title, "repository": repo_name})
            self.telegram.send_pr_notification(pr)
        else:
            self.log(f"Failed to merge PR #{pr.number}: {msg}", "ERROR")
            results["skipped"].append({"pr": pr.number, "reason": "merge_failed", "error": msg, "repository": repo_name})

    def _handle_pipeline_failure(self, pr, status: dict, results: dict) -> None:
        """Handle pipeline failure by commenting if not already done."""
        repo_name = pr.base.repo.full_name
        if not has_existing_failure_comment(pr):
            comment = build_failure_comment(pr, status["failed_checks"])
            self.github_client.comment_on_pr(pr, comment)
        results["pipeline_failures"].append({
            "action": "pipeline_failure", "pr": pr.number,
            "state": status["state"], "repository": repo_name,
        })
