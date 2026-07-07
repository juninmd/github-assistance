"""Code Reviewer Agent - Automated code review using AI analysis."""

from __future__ import annotations

from typing import Any

from github.PullRequest import PullRequest

from src.agents.base_agent import BaseAgent
from src.agents.metrics import AgentMetrics
from src.ai.factory import get_ai_client


class CodeReviewerAgent(BaseAgent):
    """Reviews PRs for code quality, best practices, and bugs using AI."""

    def __init__(self, **kwargs):
        super().__init__(name="code_reviewer", **kwargs)
        self.ai_provider = kwargs.get("ai_provider", "ollama")
        self.ai_model = kwargs.get("ai_model", "qwen3:1.7b")
        self.ai_config = kwargs.get("ai_config", {})
        self._ai_client = None

    @property
    def _ai(self):
        if self._ai_client is None:
            self._ai_client = get_ai_client(self.ai_provider, model=self.ai_model, **self.ai_config)
        return self._ai_client

    @property
    def persona(self) -> str:
        return """Code Reviewer Agent — Expert in code quality, best practices, and bug detection."""

    @property
    def mission(self) -> str:
        return """Review pull requests for code quality, maintainability, best practices, potential bugs, security issues, and performance considerations."""

    def run(self) -> dict[str, Any]:
        metrics = AgentMetrics(self.name)
        reviews_performed = []
        failed_reviews = []

        try:
            self.log("Starting code review agent...")
            repositories = self.get_allowed_repositories()
            self.log(f"Reviewing PRs in {len(repositories)} repositories")

            for repo in repositories:
                try:
                    prs = self._find_open_prs(repo)
                    self.log(f"Found {len(prs)} open PRs in {repo}")

                    for pr in prs:
                        try:
                            if self._has_recent_review(pr):
                                continue
                            result = self._review_pull_request(pr)
                            if result["success"]:
                                reviews_performed.append(result)
                                metrics.increment_processed()
                            else:
                                failed_reviews.append(result)
                                metrics.increment_failed()
                        except Exception as e:
                            self.log(f"Error reviewing PR {pr.number}: {e}", "ERROR")
                            metrics.add_error(f"PR review failed: {e}")
                            failed_reviews.append({"pr": pr.number, "error": str(e)})
                            metrics.increment_failed()

                except Exception as e:
                    self.log(f"Error processing repository {repo}: {e}", "ERROR")
                    metrics.add_error(f"Repository processing failed: {e}")

            self._send_summary({"reviews": reviews_performed, "failures": failed_reviews})

        except Exception as e:
            self.log(f"Code review agent failed: {e}", "ERROR")
            metrics.add_error(f"Agent execution failed: {e}")

        return {
            "reviews_performed": reviews_performed,
            "failed": failed_reviews,
            "metrics": metrics.finalize(),
        }

    def _find_open_prs(self, repository: str) -> list[PullRequest]:
        repo = self.github_client.get_repo(repository)
        return list(repo.get_pulls(state="open", sort="updated", direction="desc"))

    def _has_recent_review(self, pr: PullRequest) -> bool:
        try:
            bot_login = self.github_client.g.get_user().login
        except Exception:
            return False
        for comment in pr.get_issue_comments():
            if comment.user and comment.user.login == bot_login:
                return True
        return False

    def _review_pull_request(self, pr: PullRequest) -> dict[str, Any]:
        pr_number = pr.number
        files = list(pr.get_files())
        changes = []

        for f in files:
            patch = (f.patch or "")[:3000]
            changes.append(f"File: {f.filename} ({f.status}, +{f.additions}/-{f.deletions})\n```diff\n{patch}\n```")

        if not changes:
            self.log(f"PR #{pr_number}: no file changes to review")
            return {"success": True, "pr_number": pr_number, "issues_found": [], "suggestions": []}

        prompt = (
            "You are a senior code reviewer. Analyze this pull request and provide feedback.\n"
            f"PR #{pr_number}: {pr.title}\n\n"
            f"Changes:\n" + "\n---\n".join(changes[:5]) + "\n\n"
            "Respond with ONLY valid JSON:\n"
            '{"issues": [{"severity": "high|medium|low", "file": "filename", '
            '"line": null, "description": "issue description", '
            '"suggestion": "how to fix"}], "summary": "overall assessment", "score": 0-10}'
        )

        try:
            response = self._ai.generate(prompt)
            data = self._ai._extract_json_object(response) if hasattr(self._ai, "_extract_json_object") else None
            issues = data.get("issues", []) if isinstance(data, dict) else []
            summary = data.get("summary", "Review completed.") if isinstance(data, dict) else "Review completed."
        except Exception as e:
            self.log(f"AI review failed for PR #{pr_number}: {e}", "WARNING")
            return {"success": True, "pr_number": pr_number, "issues_found": [], "suggestions": [], "error": str(e)}

        self._post_review(pr, issues, summary, pr_number)
        return {"success": True, "pr_number": pr_number, "issues_found": issues, "suggestions": issues}

    def _post_review(self, pr: PullRequest, issues: list[dict], summary: str, pr_number: int) -> None:
        body_parts = ["## AI Code Review\n", f"**Summary:** {summary}\n"]
        if issues:
            body_parts.append("\n### Issues Found\n")
            for issue in issues[:10]:
                severity = issue.get("severity", "info").upper()
                file = issue.get("file", "")
                desc = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                body_parts.append(f"- **[{severity}]** {file}: {desc}")
                if suggestion:
                    body_parts.append(f"  > {suggestion}")
        else:
            body_parts.append("\nNo issues found. The code looks good! 🎉")

        body_parts.append(
            "\n---\n🤖 **Origem Automatizada**\n- **Agente:** `code_reviewer`\n"
            f"- **Modelo:** `{self.ai_provider}/{self.ai_model}`\n"
            "- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)"
        )

        try:
            pr.create_issue_comment("\n".join(body_parts))
            esc = self.telegram.escape_html
            self.telegram.send_message(
                f"👀 <b>CODE REVIEW</b> PR #{pr_number} em <code>{esc(pr.base.repo.full_name)}</code> "
                f"— {len(issues)} issues encontradas",
                parse_mode="HTML",
            )
        except Exception as e:
            self.log(f"Failed to post review for PR #{pr_number}: {e}", "WARNING")

    def _send_summary(self, results: dict) -> None:
        reviews = results.get("reviews", [])
        failures = results.get("failures", [])
        if not reviews and not failures:
            return
        lines = [
            "👀 <b>CODE REVIEWER — RESUMO</b>",
            "──────────────────────",
            f"✅ <b>Reviews realizados:</b> <code>{len(reviews)}</code>",
            f"❌ <b>Falhas:</b> <code>{len(failures)}</code>",
        ]
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
