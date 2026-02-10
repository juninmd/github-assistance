"""
Interface Developer Agent - Specializes in UI/UX implementation using modern tools.
"""
from typing import Dict, Any
from src.agents.base_agent import BaseAgent
from datetime import datetime


class InterfaceDeveloperAgent(BaseAgent):
    """
    Interface Developer Agent

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
        super().__init__(*args, name="interface_developer", **kwargs)

    def run(self) -> Dict[str, Any]:
        """
        Execute the Interface Developer workflow:
        1. Check roadmaps for UI-related features
        2. Identify UI improvement opportunities
        3. Create tasks for UI development using Stitch

        Returns:
            Summary of UI tasks created
        """
        self.log("Starting Interface Developer workflow")

        repositories = self.get_allowed_repositories()
        if not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results = {
            "ui_tasks_created": [],
            "failed": [],
            "timestamp": datetime.now().isoformat()
        }

        for repo in repositories:
            try:
                self.log(f"Analyzing UI needs for: {repo}")
                ui_analysis = self.analyze_ui_needs(repo)

                if ui_analysis.get("has_ui_work"):
                    session = self.create_ui_improvement_task(repo, ui_analysis)
                    results["ui_tasks_created"].append({
                        "repository": repo,
                        "session_id": session.get("id"),
                        "improvements": ui_analysis.get("improvements", [])
                    })
                else:
                    self.log(f"No UI work needed for {repo}")

            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({
                    "repository": repo,
                    "error": str(e)
                })

        self.log(f"Completed: {len(results['ui_tasks_created'])} UI tasks created")
        return results

    def analyze_ui_needs(self, repository: str) -> Dict[str, Any]:
        """
        Analyze repository for UI/UX improvement opportunities.

        Args:
            repository: Repository identifier

        Returns:
            UI analysis results
        """
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {
                "has_ui_work": False,
                "is_frontend_project": False,
                "ui_issues_count": 0,
                "improvements": [],
                "language": "Unknown"
            }

        # Check if repository has UI components (frontend projects)
        language = repo_info.language
        has_frontend = language in ['JavaScript', 'TypeScript', 'Vue', 'HTML']

        # Look for UI-related issues
        issues = list(repo_info.get_issues(state='open'))[:30]
        ui_issues = [
            i for i in issues
            if any(keyword in i.title.lower() or keyword in (i.body or '').lower()
                   for keyword in ['ui', 'ux', 'design', 'interface', 'component', 'layout', 'style'])
        ]

        improvements = []
        if ui_issues:
            improvements.extend([
                f"Resolve UI issue: {issue.title}"
                for issue in ui_issues[:5]  # Top 5
            ])

        # Check for missing UI documentation
        try:
            repo_info.get_contents("DESIGN.md")
        except:
            improvements.append("Create DESIGN.md with design system documentation")

        return {
            "has_ui_work": has_frontend and len(improvements) > 0,
            "is_frontend_project": has_frontend,
            "ui_issues_count": len(ui_issues),
            "improvements": improvements,
            "language": language
        }

    def create_ui_improvement_task(self, repository: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a Jules task for UI improvements using Stitch.

        Args:
            repository: Repository identifier
            analysis: UI analysis results

        Returns:
            Task creation result
        """
        improvements_text = "\n".join([f"- {imp}" for imp in analysis.get("improvements", [])])

        instructions = self.load_jules_instructions(
            variables={
                "repository": repository,
                "language": analysis.get('language', 'Unknown'),
                "improvements": improvements_text
            }
        )

        return self.create_jules_session(
            repository=repository,
            instructions=instructions,
            title=f"UI Enhancement for {repository}",
            wait_for_completion=False
        )
