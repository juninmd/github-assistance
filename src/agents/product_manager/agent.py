"""
Product Manager Agent - Responsible for roadmap planning and feature prioritization.
"""
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from github import GithubException

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client
from src.agents.product_manager import utils


def analyze_issues_with_ai(ai_client: Any, issues: list, repo_description: str) -> dict[str, Any]:
    """Module-level function for AI analysis of issues (used directly in tests)."""
    if not ai_client or not issues:
        return {"ai_summary": "No issues to analyze."}
    issues_text = "\n".join(
        f"- [{i.number}] {i.title}: {', '.join(lb.name for lb in i.labels)}"
        for i in issues
    )
    try:
        response_text = ai_client.generate(
            f"Analyze these issues for repository '{repo_description}':\n{issues_text}\n"
            "Respond with a brief strategic summary."
        )
        return {"ai_summary": response_text}
    except Exception as e:
        return {"ai_summary": f"Failed to generate AI summary: {e}"}


class ProductManagerAgent(BaseAgent):
    """Product Manager Agent — roadmap planning and feature prioritization."""

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="product_manager", **kwargs)
        self._ai_client = get_ai_client(
            provider=ai_provider or "ollama",
            model=ai_model or "qwen3:1.7b",
            **(ai_config or {})
        )

    def run(self) -> dict[str, Any]:
        """Execute the Product Manager workflow across all allowed repositories."""
        self.log("Starting Product Manager workflow")
        repositories = self.get_allowed_repositories()
        if not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results: dict[str, Any] = {
            "processed": [], "failed": [], "timestamp": datetime.now().isoformat()
        }
        for repo in repositories:
            try:
                self.log(f"Analyzing repository: {repo}")
                roadmap = self.analyze_and_create_roadmap(repo)
                results["processed"].append({"repository": repo, "roadmap": roadmap})
            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({"repository": repo, "error": str(e)})

        self.log(f"Completed: {len(results['processed'])} processed, {len(results['failed'])} failed")
        return results

    def analyze_and_create_roadmap(self, repository: str) -> dict[str, Any]:
        """Analyse a repository and create/update its ROADMAP.md via Jules."""
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            raise ValueError(f"Could not access repository {repository}")

        if self._is_roadmap_up_to_date(repo_info):
            self.log(f"ROADMAP.md is up-to-date for {repository} — skipping")
            return {"repository": repository, "skipped": True, "reason": "roadmap_up_to_date"}

        if self.has_recent_jules_session(repository, "roadmap"):
            return {"repository": repository, "skipped": True, "reason": "recent_session_exists"}

        analysis = self.analyze_repository(repository, repo_info)
        roadmap_instructions = self.generate_roadmap_instructions(repository, analysis)

        base_branch = getattr(repo_info, "default_branch", "main")
        session = self.create_jules_session(
            repository=repository,
            instructions=roadmap_instructions,
            title=f"Update Product Roadmap for {repository}",
            wait_for_completion=False,
            base_branch=base_branch,
        )

        return {
            "repository": repository,
            "session_id": session.get("id"),
            "analysis_summary": analysis.get("summary", ""),
            "priority_count": len(analysis.get("priorities", [])),
        }

    def _is_roadmap_up_to_date(self, repo: Any) -> bool:
        """Check if ROADMAP.md was updated in the last 7 days."""
        try:
            commits = repo.get_commits(path="ROADMAP.md")
            latest = next(iter(commits), None)
            if not latest:
                return False
            last_update = latest.commit.author.date.replace(tzinfo=UTC)
            return (datetime.now(UTC) - last_update) < timedelta(days=7)
        except GithubException:
            return False
        except Exception as e:
            self.log(f"Error checking ROADMAP.md freshness: {e}", "WARNING")
            return False

    def analyze_repository(self, repository: str, repo_info: Any) -> dict[str, Any]:
        """Analyse repository state using GitHub data and AI-powered insights."""
        issues = list(repo_info.get_issues(state="open"))[:50]
        bugs = [i for i in issues if any(lb.name.lower() in ["bug", "defect"] for lb in i.labels)]
        features = [i for i in issues if any(lb.name.lower() in ["feature", "enhancement"] for lb in i.labels)]
        tech_debt = [i for i in issues if any(lb.name.lower() in ["tech-debt", "refactor"] for lb in i.labels)]

        ai_result = self._analyze_issues_with_ai(issues, repo_info.description or "")

        return {
            "summary": ai_result.get("ai_summary") or f"Repository has {len(issues)} open issues",
            "priorities": ai_result.get("priorities") or [
                {"category": "Bugs", "count": len(bugs), "urgency": "high"},
                {"category": "Features", "count": len(features), "urgency": "medium"},
                {"category": "Technical Debt", "count": len(tech_debt), "urgency": "low"},
            ],
            "total_issues": len(issues),
            "repository_description": repo_info.description or "No description",
            "primary_language": repo_info.language or "Unknown",
        }

    def _analyze_issues_with_ai(self, issues: list, repo_description: str) -> dict[str, Any]:
        """Analyze issues using AI to extract summary and priorities."""
        if not self._ai_client or not issues:
            return {}
        issues_text = "\n".join(
            f"- [{i.number}] {i.title}: {', '.join(lb.name for lb in i.labels)}"
            for i in issues
        )
        prompt = (
            f"You are a Product Manager analyzing a repository.\n"
            f"Repository Description: {repo_description}\n"
            f"Here are the current open issues:\n{issues_text}\n\n"
            "Analyze these issues and provide a brief strategic summary and a list of priorities. "
            "Respond EXACTLY with the following JSON format and nothing else:\n"
            '{\n  "ai_summary": "A brief 2-sentence summary.",\n'
            '  "priorities": [{"category": "Category Name", "count": 1, "urgency": "high"}]\n}'
        )
        try:
            response_text = self._ai_client.generate(prompt)
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            self.log("Could not find JSON in AI response", "WARNING")
        except json.JSONDecodeError as e:
            self.log(f"Failed to decode JSON from AI response: {e}", "WARNING")
        except Exception as e:
            self.log(f"AI client failed to generate response: {e}", "WARNING")
        return {}

    def generate_roadmap_instructions(self, repository: str, analysis: dict[str, Any]) -> str:
        """Build Jules task instructions enriched with AI-generated insights."""
        priorities_text = "\n".join(
            f"- {p['category']}: {p['count']} items (urgency: {p['urgency']})"
            for p in analysis.get("priorities", [])
        )
        return self.load_jules_instructions(
            variables={
                "repository": repository,
                "repository_description": analysis.get("repository_description", "No description"),
                "primary_language": analysis.get("primary_language", "Unknown"),
                "total_issues": analysis.get("total_issues", 0),
                "priorities": priorities_text,
            }
        )
