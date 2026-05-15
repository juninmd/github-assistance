"""
Roadmap Generator for Product Manager Agent.
"""
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from github import GithubException

class RoadmapGenerator:
    """Handles repository analysis and roadmap instruction generation."""

    def __init__(self, agent: Any):
        self.agent = agent

    def is_roadmap_up_to_date(self, repo: Any) -> bool:
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
            self.agent.log(f"Error checking ROADMAP.md freshness: {e}", "WARNING")
            return False

    def analyze_repository(self, _repository: str, repo_info: Any) -> dict[str, Any]:
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
        if not self.agent._ai_client or not issues:
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
            response_text = self.agent._ai_client.generate(prompt)
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            self.agent.log(f"AI analysis failed: {e}", "WARNING")
        return {}

    def generate_instructions(self, repository: str, analysis: dict[str, Any]) -> str:
        """Build Jules task instructions enriched with AI-generated insights."""
        priorities_text = "\n".join(
            f"- {p['category']}: {p['count']} items (urgency: {p['urgency']})"
            for p in analysis.get("priorities", [])
        )
        return self.agent.load_jules_instructions(
            variables={
                "repository": repository,
                "repository_description": analysis.get("repository_description", "No description"),
                "primary_language": analysis.get("primary_language", "Unknown"),
                "total_issues": analysis.get("total_issues", 0),
                "priorities": priorities_text,
            }
        )
