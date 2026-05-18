"""
Intelligence Standardizer Agent - Enforces AGENTS.md and .agents structure.
"""
from typing import Any

from github.GithubException import UnknownObjectException
from github.Repository import Repository

from src.agents.base_agent import BaseAgent


class IntelligenceStandardizerAgent(BaseAgent):
    """
    Standardizes repositories with AGENTS.md and .agents folder.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, name="intelligence_standardizer", enforce_repository_allowlist=True, **kwargs)

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

        self._send_summary(results)
        return results

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        processed = results.get("processed", [])
        skipped = results.get("skipped", [])
        failed = results.get("failed", [])
        lines = [
            "🧠 <b>INTELLIGENCE STANDARDIZER</b>",
            "──────────────────────",
            f"✅ <b>Padronizados:</b> <code>{len(processed)}</code>",
            f"⏭️ <b>Pulados:</b> <code>{len(skipped)}</code>  ❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for item in processed[:5]:
            repo = item["repository"]
            method = "opencode" if item.get("via_opencode") else "jules"
            pr_url = item.get("pr_url", "")
            if pr_url:
                lines.append(f'  └ <a href="{esc(pr_url)}">{esc(repo)}</a> — {method}')
            else:
                repo_url = f"https://github.com/{repo}"
                lines.append(f'  └ <a href="{esc(repo_url)}">{esc(repo)}</a> — {method}')
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")

    def _process_repository(self, repo: Repository, results: dict[str, Any]) -> None:
        """Analyze and standardize a single repository."""
        repo_name = repo.full_name
        self.log(f"Checking intelligence structure for {repo_name}")

        analysis = self._analyze_intelligence(repo)

        is_standardized = all([
            not analysis["missing_agents_md"],
            not analysis["missing_agents_dir"],
            not analysis["missing_contributing"],
            not analysis["missing_license"]
        ])

        if is_standardized:
            self.log(f"Repository {repo_name} is already standardized.")
            results["skipped"].append({"repository": repo_name, "reason": "already_standardized"})
            return

        instructions = self.load_jules_instructions(variables={
            "repository_name": repo_name,
            "missing_agents_md": analysis["missing_agents_md"],
            "missing_agents_dir": analysis["missing_agents_dir"],
            "missing_standard_workflow": analysis["missing_standard_workflow"],
            "missing_contributing": analysis["missing_contributing"],
            "missing_license": analysis["missing_license"]
        })

        if self.has_recent_jules_session(repo_name, "Standardizing"):
            self.log(f"Jules session exists for {repo_name}. Trying opencode fallback.")
            oc_result = self.run_opencode_on_repo(
                repository=repo_name,
                instructions=instructions,
                title=f"Standardize {repo.name} Quality & Intelligence",
            )
            results["processed"].append({
                "repository": repo_name,
                "via_opencode": True,
                "pr_url": oc_result.get("pr_url"),
                **analysis,
            })
            return

        session = self.create_jules_session(
            repository=repo_name,
            instructions=instructions,
            title=f"Standardizing {repo.name} Quality & Intelligence",
            base_branch=repo.default_branch
        )

        results["processed"].append({
            "repository": repo_name,
            "session_id": session.get("id"),
            "via_opencode": False,
            **analysis,
        })

    def _analyze_intelligence(self, repo: Repository) -> dict[str, bool]:
        """Check for AGENTS.md, .agents/ folder, standard workflow, and community files."""
        checks = {
            "missing_agents_md": "AGENTS.md",
            "missing_agents_dir": ".agents",
            "missing_standard_workflow": ".github/workflows/standard.yml",
            "missing_contributing": "CONTRIBUTING.md",
            "missing_license": "LICENSE"
        }

        results = {}
        for key, path in checks.items():
            try:
                repo.get_contents(path)
                results[key] = False
            except UnknownObjectException:
                results[key] = True
            except Exception as e:
                self.log(f"Error checking {path} in {repo.full_name}: {e}", "WARNING")
                results[key] = True

        return results

