"""
Code Reviewer Agent - Automated code review using AI analysis.

This agent reviews pull requests for code quality, best practices,
and potential bugs, providing constructive feedback.
"""
from typing import Any

from github.PullRequest import PullRequest

from src.agents.base_agent import BaseAgent
from src.agents.metrics import AgentMetrics


class CodeReviewerAgent(BaseAgent):
    """
    Agent responsible for automated code review using AI.
    Reviews PRs for quality, best practices, and potential issues.
    """

    def __init__(self, **kwargs):
        super().__init__(name="code_reviewer", **kwargs)
        self.ai_provider = kwargs.get("ai_provider", "ollama")
        self.ai_model = kwargs.get("ai_model", "qwen3:1.7b")
        self.ai_config = kwargs.get("ai_config", {})

    @property
    def persona(self) -> str:
        return """Code Reviewer Agent 👀
        Expert in code quality, best practices, and bug detection.
        Provides constructive, educational feedback on pull requests."""

    @property
    def mission(self) -> str:
        return """Review pull requests for:
        - Code quality and maintainability
        - Best practices and design patterns
        - Potential bugs and security issues
        - Coding standards compliance
        - Performance considerations"""

    def run(self) -> dict[str, Any]:
        """
        Execute the code review agent workflow.

        1. Find open PRs in allowed repositories
        2. Analyze code changes using AI
        3. Post review comments with suggestions
        4. Track metrics
        """
        metrics = AgentMetrics(self.name)
        reviews_performed = []
        failed_reviews = []

        try:
            self.log("Starting code review agent...")

            # Get allowed repositories
            repositories = self.get_allowed_repositories()
            self.log(f"Reviewing PRs in {len(repositories)} repositories")

            for repo in repositories:
                try:
                    # Find open PRs
                    prs = self._find_open_prs(repo)
                    self.log(f"Found {len(prs)} open PRs in {repo}")

                    for pr in prs:
                        try:
                            # Check if already reviewed recently
                            if self._has_recent_review(pr):
                                continue

                            # Perform AI-powered code review
                            review_result = self._review_pull_request(pr)

                            if review_result["success"]:
                                reviews_performed.append(review_result)
                                metrics.increment_processed()
                            else:
                                failed_reviews.append(review_result)
                                metrics.increment_failed()
                                self.telegram.send_message(
                                    f"❌ <b>CODE REVIEWER — REVIEW FALHOU</b>\n"
                                    f"📦 <b>Repo:</b> <code>{repo}</code>  PR: <code>#{pr.number}</code>",
                                    parse_mode="HTML",
                                )

                        except Exception as e:
                            self.log(f"Error reviewing PR {pr.number}: {e}", "ERROR")
                            metrics.add_error(f"PR review failed: {str(e)}")
                            failed_reviews.append({"pr": pr.number, "error": str(e)})
                            metrics.increment_failed()
                            self.telegram.send_message(
                                f"❌ <b>CODE REVIEWER — ERRO PR</b>\n"
                                f"📦 <b>Repo:</b> <code>{repo}</code>  PR: <code>#{pr.number}</code>\n"
                                f"<pre>{self.telegram.escape_html(str(e)[:300])}</pre>",
                                parse_mode="HTML",
                            )

                except Exception as e:
                    self.log(f"Error processing repository {repo}: {e}", "ERROR")
                    metrics.add_error(f"Repository processing failed: {str(e)}")
                    self.telegram.send_message(
                        f"❌ <b>CODE REVIEWER — ERRO REPO</b>\n"
                        f"📦 <b>Repo:</b> <code>{repo}</code>\n"
                        f"<pre>{self.telegram.escape_html(str(e)[:300])}</pre>",
                        parse_mode="HTML",
                    )

            # Send summary
            self._send_summary(reviews_performed, failed_reviews)

        except Exception as e:
            self.log(f"Code review agent failed: {e}", "ERROR")
            metrics.add_error(f"Agent execution failed: {str(e)}")

        return {
            "reviews_performed": reviews_performed,
            "failed": failed_reviews,
            "metrics": metrics.finalize(),
        }

    def _find_open_prs(self, repository: str) -> list[PullRequest]:
        """Find open pull requests in a repository."""
        # Placeholder implementation
        # In production, this would use GitHub API to find open PRs
        self.log(f"Searching for open PRs in {repository}")
        return []

    def _has_recent_review(self, pr: PullRequest) -> bool:
        """Check if this PR was recently reviewed by this agent."""
        # Placeholder implementation
        # Would check PR comments for recent reviews from this bot
        return False

    def _review_pull_request(self, pr: PullRequest) -> dict[str, Any]:
        """
        Perform AI-powered code review on a pull request.

        Returns a dict with review results including:
        - success: bool
        - pr_number: int
        - issues_found: list of issues
        - suggestions: list of suggestions
        """
        # Placeholder implementation
        # In production, this would:
        # 1. Get PR diff
        # 2. Send to AI for analysis
        # 3. Parse AI response
        # 4. Post review comments

        self.log(f"Reviewing PR #{pr.number}")

        return {
            "success": True,
            "pr_number": pr.number,
            "issues_found": [],
            "suggestions": [],
        }

    def _send_summary(self, reviews: list[dict], failures: list[dict]) -> None:
        """Send a summary of code reviews to Telegram."""
        if not reviews and not failures:
            return

        lines = [
            "👀 <b>CODE REVIEWER — RESUMO</b>",
            "──────────────────────",
            f"✅ <b>Reviews realizados:</b> <code>{len(reviews)}</code>",
            f"❌ <b>Falhas:</b> <code>{len(failures)}</code>",
        ]

        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
