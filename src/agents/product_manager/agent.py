"""
Product Manager Agent - Responsible for roadmap planning and feature prioritization.
"""
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client
from src.agents.product_manager import utils


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
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="product_manager", **kwargs)
        self._ai_client = get_ai_client(
            provider=ai_provider or "gemini",
            model=ai_model,
            **(ai_config or {})
        )

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

        # Skip if ROADMAP.md was recently updated and no new issues
        if utils.is_roadmap_up_to_date(repo_info, self.log):
            self.log(f"ROADMAP.md is up-to-date for {repository} — skipping")
            return {"repository": repository, "skipped": True, "reason": "roadmap_up_to_date"}

        # Skip if there's already a recent Jules session for this repo's roadmap
        if self.has_recent_jules_session(repository, "roadmap"):
            return {"repository": repository, "skipped": True, "reason": "recent_session_exists"}

        # Analyze repository
        analysis = utils.analyze_repository(repository, repo_info, self._ai_client, self.log)

        # Generate roadmap instructions for Jules
        roadmap_instructions = utils.generate_roadmap_instructions(
            analysis, self.load_jules_instructions, repository
        )

        # Create Jules task to generate/update ROADMAP.md
        base_branch = getattr(repo_info, "default_branch", "main")

        session = self.create_jules_session(
            repository=repository,
            instructions=roadmap_instructions,
            title=f"Update Product Roadmap for {repository}",
            wait_for_completion=False,  # Run async
            base_branch=base_branch,
        )

        return {
            "repository": repository,
            "session_id": session.get("id"),
            "analysis_summary": analysis.get("summary", ""),
            "priority_count": len(analysis.get("priorities", []))
        }
