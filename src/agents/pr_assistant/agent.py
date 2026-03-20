"""
PR Assistant Agent - Auto-merges PRs and manages pipelines.
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
from src.ai import get_ai_client

ALLOWED_AUTHORS = [
    "juninmd", "Copilot", "Jules da Google", "google-labs-jules",
    "google-labs-jules[bot]", "gemini-code-assist", "gemini-code-assist[bot]",
    "imgbot[bot]", "renovate[bot]", "dependabot[bot]",
]

BOT_REVIEWS = ["Jules da Google", "google-labs-jules", "gemini-code-assist"]


class PRAssistantAgent(BaseAgent):
    """Monitors and processes PRs across all repositories."""

    def __init__(
        self,
        *args,
        ai_provider: str = "ollama",
        ai_model: str = "qwen3:1.7b",
        target_owner: str = "juninmd",
        min_pr_age_minutes: int = 10,
        pr_ref: str | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="pr_assistant", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = target_owner
        self.min_pr_age_minutes = min_pr_age_minutes
        self.pr_ref = pr_ref
        self.ai_client = get_ai_client(ai_provider, model=ai_model, **(kwargs.get("ai_config") or {}))

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def uses_repository_allowlist(self) -> bool:
        return False

    def run(self) -> dict[str, Any]:
        """Execute the PR assistant workflow."""
        self.log("Starting PR Assistant workflow")
        results: dict[str, Any] = {
            "merged": [], "conflicts_resolved": [], "pipeline_failures": [], "skipped": [],
            "timestamp": datetime.now().isoformat(),
        }
        for pr in self._get_prs_to_process():
            try:
                self._process_pr(pr, results)
            except Exception as e:
                self.log(f"Error processing PR #{pr.number}: {e}", "ERROR")
                results["skipped"].append({
                    "pr": pr.number,
                    "title": getattr(pr, "title", "Unknown Title"),
                    "reason": "error",
                    "error": str(e),
                })

        build_and_send_summary(results, self.telegram, self.target_owner)
        return results

    # ── PR discovery ──────────────────────────────────────────────────────

    def _get_prs_to_process(self) -> list:
        if self.pr_ref:
            return self._get_pr_from_ref(self.pr_ref)
        prs = []
        for issue in self.github_client.search_prs(self.target_owner):
            try:
                prs.append(self.github_client.get_pr_from_issue(issue))
            except Exception as e:
                self.log(f"Could not resolve PR from issue: {e}", "WARNING")
        return prs

    def _get_pr_from_ref(self, ref: str) -> list:
        """Resolve a single PR from a 'owner/repo#number' reference."""
        try:
            repo_slug, number = ref.rsplit("#", 1)
            repo = self.github_client.get_repo(repo_slug)
            return [repo.get_pull(int(number))]
        except Exception as e:
            self.log(f"Could not resolve PR ref {ref}: {e}", "ERROR")
            return []

    # ── PR processing ─────────────────────────────────────────────────────

    def _process_pr(self, pr, results: dict) -> None:
        """Process a single PR through the full pipeline."""
        repo_name = pr.base.repo.full_name
        self.log(f"Processing PR #{pr.number} in {repo_name}")

        if not self._is_pr_old_enough(pr):
            return

        labels = {lb.name for lb in pr.get_labels()}
        if "auto-merge-skip" in labels:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "auto-merge-skip", "repository": repo_name,
            })
            return

        author = pr.user.login if pr.user else "unknown"
        if not self._is_trusted_author(author):
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "untrusted_author", "repository": repo_name,
            })
            return

        self._try_accept_suggestions(pr)

        if pr.mergeable is False:
            self._handle_conflicts(pr, results)
            return
        if pr.mergeable is None:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "mergeable_unknown", "repository": repo_name,
            })
            return

        status = check_pipeline_status(pr)
        if status["state"] == "success":
            self._try_merge(pr, results)
        elif status["state"] in ("failure", "error"):
            self._handle_pipeline_failure(pr, status, results)
        else:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": f"pipeline_{status['state']}", "repository": repo_name,
            })

    # ── Guards ────────────────────────────────────────────────────────────

    def _is_pr_old_enough(self, pr) -> bool:
        if not pr.created_at:
            return True
        age = datetime.now(UTC) - pr.created_at.replace(tzinfo=UTC)
        return age >= timedelta(minutes=self.min_pr_age_minutes)

    def _is_trusted_author(self, login: str) -> bool:
        return login in ALLOWED_AUTHORS

    # ── Suggestions ───────────────────────────────────────────────────────

    def _try_accept_suggestions(self, pr) -> None:
        try:
            _success, _msg, count = self.github_client.accept_review_suggestions(pr, BOT_REVIEWS)
            if count > 0:
                self.log(f"Applied {count} suggestions on PR #{pr.number}")
        except Exception as e:
            self.log(f"Error applying suggestions on PR #{pr.number}: {e}", "WARNING")

    # ── Merge ─────────────────────────────────────────────────────────────

    def _try_merge(self, pr, results: dict) -> None:
        should_merge, reason = self._evaluate_comments_with_llm(pr)
        if not should_merge:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": f"llm_rejected: {reason}", "repository": pr.base.repo.full_name,
            })
            return

        success, msg = self.github_client.merge_pr(pr)
        if success:
            results["merged"].append({
                "action": "merged", "pr": pr.number, "title": pr.title,
                "repository": pr.base.repo.full_name,
            })
            self.telegram.send_pr_notification(pr)
        else:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "merge_failed", "error": msg,
            })

    def _evaluate_comments_with_llm(self, pr) -> tuple[bool, str]:
        """Use AI to evaluate human PR comments and decide whether to merge."""
        try:
            comments = list(pr.get_issue_comments())
            human = [
                c for c in comments[-10:]
                if c.user and not self._is_trusted_author(c.user.login)
            ]
            if not human:
                return True, "No human review"
            text = "\n".join(f"@{c.user.login}: {c.body[:300]}" for c in human)
            response = self.ai_client.generate(
                f"Analyze PR comments:\n{text}\nReply: MERGE or REJECT."
            )
            if not response:
                return True, "Empty response"
            return ("REJECT" not in response.upper(), response)
        except Exception:
            return True, "Evaluation failed"

    # ── Conflicts ─────────────────────────────────────────────────────────

    def _handle_conflicts(self, pr, results: dict) -> None:
        """Try to resolve conflicts automatically, notify on result."""
        success, msg = resolve_conflicts_autonomously(pr)
        if success:
            results["conflicts_resolved"].append({
                "pr": pr.number, "title": pr.title,
                "repository": pr.base.repo.full_name,
            })
            self._notify_conflict_resolved(pr, msg)
        else:
            results["skipped"].append({
                "pr": pr.number, "title": pr.title,
                "reason": "has_conflicts", "repository": pr.base.repo.full_name,
            })
            self._notify_conflicts(pr)

    def _notify_conflict_resolved(self, pr, msg: str) -> None:
        """Post GitHub comment and Telegram notification about resolved conflicts."""
        author = f"@{pr.user.login}" if pr.user else "@contributor"
        repo_name = pr.base.repo.full_name
        comment = (
            f"✅ **Conflitos de Merge Resolvidos**\n\n"
            f"Oi {author}! Os conflitos de merge do PR **#{pr.number}** foram resolvidos automaticamente.\n\n"
            f"**Detalhes:** {msg}"
        )
        try:
            self.github_client.comment_on_pr(pr, comment)
        except Exception as e:
            self.log(f"Failed to comment on PR #{pr.number}: {e}", "WARNING")

        try:
            text = self.telegram.escape(
                f"✅ Conflitos resolvidos em {repo_name} PR\\#{pr.number}\n{msg}"
            )
            self.telegram.send_message(text, parse_mode="MarkdownV2")
        except Exception as e:
            self.log(f"Failed to send Telegram notification: {e}", "WARNING")

    def _notify_conflicts(self, pr) -> None:
        """Notify about unresolved merge conflicts (once only)."""
        try:
            existing = [c for c in pr.get_issue_comments() if "⚠️ **Conflitos de Merge Detectados**" in c.body]
            if existing:
                return
            self.github_client.comment_on_pr(
                pr,
                "⚠️ **Conflitos de Merge Detectados**\n\n"
                "Este PR tem conflitos de merge que não puderam ser resolvidos automaticamente. "
                "Por favor, resolva manualmente.",
            )
        except Exception as e:
            self.log(f"Error notifying conflicts for PR #{pr.number}: {e}", "WARNING")

    # ── Pipeline failure ──────────────────────────────────────────────────

    def _handle_pipeline_failure(self, pr, status: dict, results: dict) -> None:
        if not has_existing_failure_comment(pr):
            comment = build_failure_comment(pr, status.get("failed_checks", []))
            self.github_client.comment_on_pr(pr, comment)
        results["pipeline_failures"].append({
            "action": "pipeline_failure", "pr": pr.number, "title": pr.title,
            "state": status["state"], "repository": pr.base.repo.full_name,
        })
