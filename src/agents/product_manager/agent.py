"""
Product Manager Agent - Responsible for roadmap planning and feature prioritization.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from github import GithubException

from src.agents.base_agent import BaseAgent
from src.agents.product_manager.ai_analysis import analyze_issues_with_ai
from src.ai_client import get_ai_client


class ProductManagerAgent(BaseAgent):
    """
    Product Manager Agent

    Reads instructions from instructions.md file.
    """

    @property
    def persona(self) -> str:
        """Load persona from instructions.md"""
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        """Load mission from instructions.md"""
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str = "ollama",
        ai_model: str = "llama3",
        ai_config: dict | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="product_manager", **kwargs)
        try:
            self._ai_client = get_ai_client(ai_provider, model=ai_model, **(ai_config or {}))
        except Exception as exc:
            self.log(f"AI client unavailable: {exc}", "WARNING")
            self._ai_client = None

    def run(self) -> dict[str, Any]:
        """Execute the Product Manager workflow across all allowed repositories."""
        self.log("Starting Product Manager workflow")

        repositories = self.get_allowed_repositories()
        if not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results = {
            "processed": [],
            "failed": [],
            "timestamp": datetime.now().isoformat()
        }

        for repo in repositories:
            try:
                self.log(f"Analyzing repository: {repo}")
                roadmap = self.analyze_and_create_roadmap(repo)
                results["processed"].append({
                    "repository": repo,
                    "roadmap": roadmap
                })
            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({
                    "repository": repo,
                    "error": str(e)
                })

        self.log(f"Completed: {len(results['processed'])} processed, {len(results['failed'])} failed")
        return results

    def analyze_and_create_roadmap(self, repository: str) -> dict[str, Any]:
        """Analyse a repository and create/update its ROADMAP.md via Jules."""
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            raise ValueError(f"Could not access repository {repository}")

        # Skip if ROADMAP.md was recently updated and no new issues
        if self._is_roadmap_up_to_date(repo_info):
            self.log(f"ROADMAP.md is up-to-date for {repository} — skipping")
            return {"repository": repository, "skipped": True, "reason": "roadmap_up_to_date"}

        # Skip if there's already a recent Jules session for this repo's roadmap
        if self.has_recent_jules_session(repository, "roadmap"):
            return {"repository": repository, "skipped": True, "reason": "recent_session_exists"}

        # Analyze repository
        analysis = self.analyze_repository(repository, repo_info)

        # Generate roadmap instructions for Jules
        roadmap_instructions = self.generate_roadmap_instructions(repository, analysis)

        # Create Jules task to generate/update ROADMAP.md
        session = self.create_jules_session(
            repository=repository,
            instructions=roadmap_instructions,
            title=f"Update Product Roadmap for {repository}",
            wait_for_completion=False  # Run async
        )

        return {
            "repository": repository,
            "session_id": session.get("id"),
            "analysis_summary": analysis.get("summary", ""),
            "priority_count": len(analysis.get("priorities", []))
        }

    def _is_roadmap_up_to_date(self, repo) -> bool:
        """Check if ROADMAP.md was updated in the last 7 days."""
        try:
            commits = repo.get_commits(path="ROADMAP.md")
            latest = next(iter(commits), None)
            if not latest:
                return False  # No ROADMAP.md yet — should create one

            last_update = latest.commit.author.date.replace(tzinfo=UTC)
            age = datetime.now(UTC) - last_update
            if age < timedelta(days=7):
                self.log(f"ROADMAP.md updated {age.days}d ago — still fresh")
                return True
        except GithubException:
            return False  # ROADMAP.md doesn't exist or error
        except Exception as e:
            self.log(f"Error checking ROADMAP.md freshness: {e}", "WARNING")
        return False

    def analyze_repository(self, repository: str, repo_info: Any) -> dict[str, Any]:
        """Analyse repository state using GitHub data and AI-powered insights."""
        self.log(f"Analyzing {repository}")

        # Get open issues and PRs
        issues = list(repo_info.get_issues(state='open'))[:50]  # Limit to 50

        # Label-based categorisation
        bugs = [i for i in issues if any(lb.name.lower() in ['bug', 'defect'] for lb in i.labels)]
        features = [i for i in issues if any(lb.name.lower() in ['feature', 'enhancement'] for lb in i.labels)]
        tech_debt = [i for i in issues if any(lb.name.lower() in ['tech-debt', 'refactor'] for lb in i.labels)]

        # AI-powered strategic analysis
        ai_result = (
            analyze_issues_with_ai(self._ai_client, issues, repo_info.description or "")
            if self._ai_client
            else {}
        )

        return {
            "summary": ai_result.get("ai_summary") or f"Repository has {len(issues)} open issues",
            "ai_priorities": ai_result.get("ai_priorities", []),
            "ai_highlights": ai_result.get("ai_highlights", []),
            "priorities": [
                {"category": "Bugs", "count": len(bugs), "urgency": "high"},
                {"category": "Features", "count": len(features), "urgency": "medium"},
                {"category": "Technical Debt", "count": len(tech_debt), "urgency": "low"},
            ],
            "total_issues": len(issues),
            "repository_description": repo_info.description or "No description",
            "main_language": repo_info.language or "Unknown",
        }

    def generate_roadmap_instructions(self, repository: str, analysis: dict[str, Any]) -> str:
        """Build Jules task instructions enriched with AI-generated insights."""
        priorities_text = "\n".join(
            f"- {p['category']}: {p['count']} items (urgency: {p['urgency']})"
            for p in analysis.get("priorities", [])
        )
        ai_priorities = "\n".join(f"- {p}" for p in analysis.get("ai_priorities", []))
        ai_highlights = "\n".join(f"- {h}" for h in analysis.get("ai_highlights", []))
        return self.load_jules_instructions(
            variables={
                "repository": repository,
                "repository_description": analysis.get("repository_description", "No description"),
                "main_language": analysis.get("main_language", "Unknown"),
                "total_issues": analysis.get("total_issues", 0),
                "priorities": priorities_text,
                "ai_summary": analysis.get("summary", ""),
                "ai_priorities": ai_priorities or priorities_text,
                "ai_highlights": ai_highlights or "No specific highlights identified.",
            }
        )
