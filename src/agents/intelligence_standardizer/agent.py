"""
Intelligence Standardizer Agent - Enforces AGENTS.md and .agents structure.
"""
from typing import Any
from github.GithubException import UnknownObjectException

from src.agents.base_agent import BaseAgent


class IntelligenceStandardizerAgent(BaseAgent):
    """
    Standardizes repositories with AGENTS.md and .agents folder.
    """

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        """Execute the standardization workflow on the last 10 repos."""
        self.log("Starting Intelligence Standardizer workflow")
        repos = self.github_client.get_user_repos(sort="updated", limit=10)
        
        results = {
            "processed": [],
            "skipped": [],
            "failed": []
        }

        for repo in repos:
            try:
                self._process_repository(repo, results)
            except Exception as e:
                self.log(f"Failed to process {repo.full_name}: {e}", "ERROR")
                results["failed"].append({"repository": repo.full_name, "error": str(e)})

        return results

    def _process_repository(self, repo: Any, results: dict[str, Any]) -> None:
        """Analyze and standardize a single repository."""
        repo_name = repo.full_name
        self.log(f"Checking intelligence structure for {repo_name}")

        analysis = self._analyze_intelligence(repo)
        
        if not analysis["missing_agents_md"] and not analysis["missing_agents_dir"]:
            self.log(f"Repository {repo_name} is already standardized.")
            results["skipped"].append({"repository": repo_name, "reason": "already_standardized"})
            return

        if self.has_recent_jules_session(repo_name, "Standardizing"):
            self.log(f"Session already exists for {repo_name}. Skipping.")
            results["skipped"].append({"repository": repo_name, "reason": "recent_session_exists"})
            return

        instructions = self.load_jules_instructions(variables={
            "repository_name": repo_name,
            "missing_agents_md": analysis["missing_agents_md"],
            "missing_agents_dir": analysis["missing_agents_dir"]
        })

        session = self.create_jules_session(
            repository=repo_name,
            instructions=instructions,
            title=f"Standardizing {repo.name} Intelligence System",
            base_branch=repo.default_branch
        )

        results["processed"].append({
            "repository": repo_name,
            "session_id": session.get("id"),
            "missing_md": analysis["missing_agents_md"],
            "missing_dir": analysis["missing_agents_dir"]
        })

    def _analyze_intelligence(self, repo: Any) -> dict[str, bool]:
        """Check for AGENTS.md and .agents/ folder."""
        missing_md = False
        missing_dir = False

        try:
            repo.get_contents("AGENTS.md")
        except UnknownObjectException:
            missing_md = True
        except Exception as e:
            self.log(f"Error checking AGENTS.md in {repo.full_name}: {e}", "WARNING")

        try:
            repo.get_contents(".agents")
        except UnknownObjectException:
            missing_dir = True
        except Exception as e:
            self.log(f"Error checking .agents folder in {repo.full_name}: {e}", "WARNING")

        return {"missing_agents_md": missing_md, "missing_agents_dir": missing_dir}
