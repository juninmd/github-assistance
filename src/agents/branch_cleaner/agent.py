from typing import Any

from github import GithubException

from src.agents.base_agent import BaseAgent


class BranchCleanerAgent(BaseAgent):
    """
    Agent that identifies and deletes merged branches across all repositories.
    """

    def __init__(self, **kwargs):
        super().__init__(name="branch_cleaner", enforce_repository_allowlist=False, **kwargs)

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        """Run the branch cleaning process across all allowed repositories."""
        repositories = self.get_allowed_repositories()
        results = {
            "processed_repos": 0,
            "deleted_branches": [],
            "failed_branches": [],
            "skipped_repos": [],
        }

        self.log(f"Starting branch cleaning for {len(repositories)} repositories...")

        for repo_name in repositories:
            try:
                repo = self.github_client.get_repo(repo_name)
                if not repo:
                    self.log(f"Repository {repo_name} not found, skipping.", "WARNING")
                    results["skipped_repos"].append(repo_name)
                    continue

                self.log(f"Cleaning repository: {repo_name}")

                # Dynamic discovery of default branch (NEVER DELETE THIS)
                default_branch = repo.default_branch
                self.log(f"Default branch for {repo_name} is '{default_branch}'")

                branches = list(repo.get_branches())
                repo_deleted = []

                for branch in branches:
                    # Security checks
                    if branch.name == default_branch:
                        continue

                    if branch.protected:
                        self.log(f"Skipping protected branch: {branch.name}")
                        continue

                    # Check if branch is merged into default_branch
                    try:
                        comparison = repo.compare(default_branch, branch.name)
                        # If ahead_by is 0, it means all commits in 'branch' are already in 'default_branch'
                        if comparison.ahead_by == 0:
                            self.log(f"Deleting merged branch: {branch.name} from {repo_name}")

                            # Perform deletion
                            ref = repo.get_git_ref(f"heads/{branch.name}")
                            ref.delete()

                            repo_deleted.append(f"{repo_name}#{branch.name}")
                            results["deleted_branches"].append(f"{repo_name}#{branch.name}")
                        else:
                            self.log(f"Branch {branch.name} is NOT merged (ahead by {comparison.ahead_by}), skipping.")
                    except GithubException as e:
                        self.log(f"Failed to check/delete branch {branch.name}: {e}", "ERROR")
                        results["failed_branches"].append(f"{repo_name}#{branch.name}")

                results["processed_repos"] += 1
                if repo_deleted:
                    self.log(f"Deleted {len(repo_deleted)} branches from {repo_name}")

            except Exception as e:
                self.log(f"Error processing repository {repo_name}: {e}", "ERROR")
                results["skipped_repos"].append(repo_name)

        self.log(f"Branch cleaning finished. Total deleted: {len(results['deleted_branches'])}")
        self._send_summary(results)
        return results

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        deleted = results.get("deleted_branches", [])
        failed = results.get("failed_branches", [])
        lines = [
            "🌿 <b>BRANCH CLEANER</b>",
            "──────────────────────",
            f"🗑️ <b>Branches deletadas:</b> <code>{len(deleted)}</code>",
            f"❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for branch in deleted[:10]:
            lines.append(f"  └ <code>{esc(branch)}</code>")
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
