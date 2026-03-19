"""
PR Assistant Agent - Auto-merges PRs and manages pipelines.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant.pipeline import (
    build_failure_comment,
    check_pipeline_status,
    has_existing_failure_comment,
)
from src.agents.pr_assistant.telegram_summary import build_and_send_summary
from src.agents.pr_assistant.utils import get_prs_to_process, is_trusted_author
from src.ai_client import get_ai_client

ALLOWED_AUTHORS = [
    "juninmd", "Copilot", "Jules da Google", "google-labs-jules",
    "google-labs-jules[bot]", "gemini-code-assist", "gemini-code-assist[bot]",
    "imgbot[bot]", "renovate[bot]", "dependabot[bot]",
]

BOT_REVIEWS = ["Jules da Google", "google-labs-jules", "gemini-code-assist"]

class PRAssistantAgent(BaseAgent):
    """Monitors and processes PRs across all repositories."""

    def __init__(self, *args, ai_provider: str = "gemini", ai_model: str = "gemini-2.5-flash", **kwargs):
        super().__init__(*args, name="pr_assistant", enforce_repository_allowlist=False, **kwargs)
        self.min_pr_age_minutes = kwargs.get("min_pr_age_minutes", 10)
        self.pr_ref = kwargs.get("pr_ref")
        self.ai_client = get_ai_client(ai_provider, model=ai_model, **(kwargs.get("ai_config") or {}))

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        """Execute the PR assistant workflow."""
        self.log("Starting PR Assistant workflow")
        results = {"merged": [], "pipeline_failures": [], "skipped": [], "timestamp": datetime.now().isoformat()}
        prs = get_prs_to_process(self.github_client, self.target_owner, self.pr_ref)
        
        for pr in prs:
            try:
                self._process_pr(pr, results)
            except Exception as e:
                self.log(f"Error processing PR #{pr.number}: {e}", "ERROR")
                results["skipped"].append({"pr": pr.number, "title": getattr(pr, "title", "?"), "reason": "error"})

        build_and_send_summary(results, self.telegram, self.target_owner)
        return results

    def _process_pr(self, pr, results: dict) -> None:
        """Process a single PR through the full pipeline."""
        repo_name = pr.base.repo.full_name
        self.log(f"Processing PR #{pr.number} in {repo_name}")

        if not self._is_old_enough(pr):
            return

        author = pr.user.login if pr.user else "unknown"
        if not is_trusted_author(author, ALLOWED_AUTHORS):
            results["skipped"].append({"pr": pr.number, "title": pr.title, "reason": "untrusted", "repository": repo_name})
            return

        self._try_accept_suggestions(pr)

        if pr.mergeable is False:
            results["skipped"].append({"pr": pr.number, "title": pr.title, "reason": "has_conflicts", "repository": repo_name})
            return
        if pr.mergeable is None:
            return

        status = check_pipeline_status(pr)
        if status["state"] == "success":
            self._try_merge(pr, results)
        elif status["state"] in ("failure", "error"):
            self._handle_failure(pr, status, results)
        else:
            results["skipped"].append({"pr": pr.number, "title": pr.title, "reason": f"pipeline_{status['state']}"})

    def _is_old_enough(self, pr) -> bool:
        if not pr.created_at: return True
        age = datetime.now(UTC) - pr.created_at.replace(tzinfo=UTC)
        return age >= timedelta(minutes=self.min_pr_age_minutes)

    def _try_accept_suggestions(self, pr) -> None:
        try:
            success, msg, count = self.github_client.accept_review_suggestions(pr, BOT_REVIEWS)
            if count > 0: self.log(f"Applied {count} suggestions on PR #{pr.number}")
        except Exception as e:
            self.log(f"Error suggestions on PR #{pr.number}: {e}", "WARNING")

    def _try_merge(self, pr, results: dict) -> None:
        should_merge, reason = self._evaluate_comments(pr)
        if not should_merge:
            results["skipped"].append({"pr": pr.number, "title": pr.title, "reason": "llm_rejected", "repository": pr.base.repo.full_name})
            return

        success, msg = self.github_client.merge_pr(pr)
        if success:
            results["merged"].append({"action": "merged", "pr": pr.number, "title": pr.title, "repository": pr.base.repo.full_name})
            self.telegram.send_pr_notification(pr)
        else:
            results["skipped"].append({"pr": pr.number, "title": pr.title, "reason": "merge_failed", "error": msg})

    def _evaluate_comments(self, pr) -> tuple[bool, str]:
        try:
            comments = list(pr.get_issue_comments())
            human = [c for c in comments[-10:] if c.user and not is_trusted_author(c.user.login, ALLOWED_AUTHORS)]
            if not human: return True, "No human review"
            text = "\n".join(f"@{c.user.login}: {c.body[:300]}" for c in human)
            response = self.ai_client.generate(f"Analyze PR comments:\n{text}\nReply: MERGE or REJECT.")
            return ("REJECT" not in response.upper(), response)
        except Exception:
            return True, "Evaluation failed"

    def _handle_failure(self, pr, status: dict, results: dict) -> None:
        if not has_existing_failure_comment(pr):
            comment = build_failure_comment(pr, status["failed_checks"])
            self.github_client.comment_on_pr(pr, comment)
        results["pipeline_failures"].append({
            "action": "pipeline_failure", "pr": pr.number, "title": pr.title,
            "state": status["state"], "repository": pr.base.repo.full_name,
        })
