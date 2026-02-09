"""
Product Manager Agent - Responsible for roadmap planning and feature prioritization.
"""
from typing import Dict, Any, List
from pathlib import Path
from src.agents.base_agent import BaseAgent
import json
from datetime import datetime


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, name="product_manager", **kwargs)

    def run(self) -> Dict[str, Any]:
        """
        Execute the Product Manager workflow:
        1. Iterate through allowed repositories
        2. Analyze each repository's current state
        3. Generate/update roadmap
        4. Create Jules tasks for roadmap documentation

        Returns:
            Summary of roadmaps created/updated
        """
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

    def analyze_and_create_roadmap(self, repository: str) -> Dict[str, Any]:
        """
        Analyze a repository and create/update its roadmap.

        Args:
            repository: Repository identifier

        Returns:
            Roadmap summary
        """
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            raise ValueError(f"Could not access repository {repository}")

        # Analyze repository
        analysis = self.analyze_repository(repository, repo_info)

        # Generate roadmap instructions for Jules
        roadmap_instructions = self.generate_roadmap_instructions(repository, analysis)

        # Create Jules task to generate/update ROADMAP.md
        task = self.create_jules_task(
            repository=repository,
            instructions=roadmap_instructions,
            title=f"Update Product Roadmap for {repository}",
            wait_for_completion=False  # Run async
        )

        return {
            "repository": repository,
            "task_id": task.get("task_id"),
            "analysis_summary": analysis.get("summary", ""),
            "priority_count": len(analysis.get("priorities", []))
        }

    def analyze_repository(self, repository: str, repo_info: Any) -> Dict[str, Any]:
        """
        Analyze repository to understand current state and needs.

        Args:
            repository: Repository identifier
            repo_info: GitHub repository object

        Returns:
            Analysis results
        """
        self.log(f"Analyzing {repository}")

        # Get open issues and PRs
        issues = list(repo_info.get_issues(state='open'))[:50]  # Limit to 50

        # Categorize issues
        bugs = [i for i in issues if any(label.name.lower() in ['bug', 'defect'] for label in i.labels)]
        features = [i for i in issues if any(label.name.lower() in ['feature', 'enhancement'] for label in i.labels)]
        technical_debt = [i for i in issues if any(label.name.lower() in ['tech-debt', 'refactor'] for label in i.labels)]

        return {
            "summary": f"Repository has {len(issues)} open issues",
            "priorities": [
                {"category": "Bugs", "count": len(bugs), "urgency": "high"},
                {"category": "Features", "count": len(features), "urgency": "medium"},
                {"category": "Technical Debt", "count": len(technical_debt), "urgency": "low"}
            ],
            "total_issues": len(issues),
            "repository_description": repo_info.description or "No description",
            "main_language": repo_info.language or "Unknown"
        }

    def generate_roadmap_instructions(self, repository: str, analysis: Dict[str, Any]) -> str:
        """
        Generate detailed instructions for Jules to create a roadmap.

        Args:
            repository: Repository identifier
            analysis: Repository analysis results

        Returns:
            Detailed instructions
        """
        priorities_text = "\n".join([
            f"- {p['category']}: {p['count']} items (urgency: {p['urgency']})"
            for p in analysis.get("priorities", [])
        ])

        return self.load_jules_instructions(
            variables={
                "repository": repository,
                "repository_description": analysis.get('repository_description', 'No description'),
                "main_language": analysis.get('main_language', 'Unknown'),
                "total_issues": analysis.get('total_issues', 0),
                "priorities": priorities_text
            }
        )
