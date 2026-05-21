from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from github import GithubException

from src.agents.base_agent import BaseAgent


_MAX_BRANCH_WORKERS = 5


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

    def _process_branch(self, repo, default_branch: str, branch, repo_name: str) -> str | None:
        """Check and delete a single branch if merged. Returns branch id or None."""
        if branch.name == default_branch or branch.protected:
            return None
        try:
            comparison = repo.compare(default_branch, branch.name)
            if comparison.ahead_by == 0:
                ref = repo.get_git_ref(f"heads/{branch.name}")
                ref.delete()
                self.log(f"Deleted merged branch: {branch.name} from {repo_name}")
                return f"{repo_name}#{branch.name}"
            self.log(f"Branch {branch.name} is NOT merged (ahead by {comparison.ahead_by}), skipping.")
        except GithubException as e:
            self.log(f"Failed to check/delete branch {branch.name}: {e}", "ERROR")
            self.telegram.send_message(
                f"❌ <b>BRANCH CLEANER — FALHA AO DELETAR</b>\n"
                f"📦 <code>{self.telegram.escape_html(repo_name)}</code>  "
                f"branch: <code>{self.telegram.escape_html(branch.name)}</code>\n"
                f"<pre>{self.telegram.escape_html(str(e)[:200])}</pre>",
                parse_mode="HTML",
            )
        return None

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
                    self.telegram.send_message(
                        f"⚠️ <b>BRANCH CLEANER — REPO NÃO ENCONTRADO</b>\n"
                        f"📦 <code>{self.telegram.escape_html(repo_name)}</code>",
                        parse_mode="HTML",
                    )
                    continue

                self.log(f"Cleaning repository: {repo_name}")
                default_branch = repo.default_branch
                self.log(f"Default branch for {repo_name} is '{default_branch}'")

                branches = list(repo.get_branches())
                repo_deleted = []

                with ThreadPoolExecutor(max_workers=min(len(branches), _MAX_BRANCH_WORKERS)) as executor:
                    futures = {
                        executor.submit(self._process_branch, repo, default_branch, b, repo_name): b
                        for b in branches
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        if result:
                            repo_deleted.append(result)
                            results["deleted_branches"].append(result)

                results["processed_repos"] += 1
                if repo_deleted:
                    self.log(f"Deleted {len(repo_deleted)} branches from {repo_name}")

            except Exception as e:
                self.log(f"Error processing repository {repo_name}: {e}", "ERROR")
                results["skipped_repos"].append(repo_name)
                self.telegram.send_message(
                    f"❌ <b>BRANCH CLEANER — ERRO REPO</b>\n"
                    f"📦 <code>{self.telegram.escape_html(repo_name)}</code>\n"
                    f"<pre>{self.telegram.escape_html(str(e)[:300])}</pre>",
                    parse_mode="HTML",
                )

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
