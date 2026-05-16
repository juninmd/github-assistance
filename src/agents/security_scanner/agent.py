"""
Security Scanner Agent - Scans GitHub repositories for exposed secrets using gitleaks.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.security_scanner import scanner as _scanner
from src.agents.security_scanner.telegram_summary import (
    build_and_send_report,
    send_error_notification,
)


class SecurityScannerAgent(BaseAgent):
    """
    Scans all GitHub repositories for exposed credentials using gitleaks.
    Sends sanitised reports via Telegram without revealing actual secret values.
    """

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(self, *args, target_owner: str = "juninmd", **kwargs):
        super().__init__(
            *args, name="security_scanner", enforce_repository_allowlist=False,
            target_owner=target_owner, **kwargs
        )
        self.target_owner = target_owner
        self._commit_author_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Delegated scanning helpers (kept as instance methods so tests pass)
    # ------------------------------------------------------------------

    def _ensure_gitleaks_installed(self) -> bool:
        return _scanner.ensure_gitleaks_installed(self.log)

    def _scan_repository(self, repo_name: str, default_branch: str = "main") -> dict[str, Any]:
        return _scanner.scan_repository(repo_name, default_branch, self.log)

    def _sanitize_findings(self, findings: list[dict]) -> list[dict]:
        return _scanner.sanitize_findings(findings)

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Execute Security Scanner workflow."""
        self.log("Starting Security Scanner workflow")
        self.log(f"Target owner: {self.target_owner}")

        results: dict[str, Any] = {
            "total_repositories": 0,
            "scanned": 0,
            "failed": 0,
            "total_findings": 0,
            "all_repositories": [],
            "repositories_with_findings": [],
            "scan_errors": [],
            "timestamp": datetime.now().isoformat(),
        }

        if not self._ensure_gitleaks_installed():
            error_msg = "Failed to install gitleaks. Cannot proceed with security scan."
            self.log(error_msg, "ERROR")
            results["error"] = error_msg
            self._send_error_notification(error_msg)
            return results

        repositories = self._get_all_repositories()
        results["total_repositories"] = len(repositories)
        results["all_repositories"] = repositories

        if not repositories:
            self.log("No repositories found to scan")
            self._send_notification(results)
            return results

        scan_lock = __import__('threading').Lock()

        def _scan_single(repo_info: dict) -> dict[str, Any]:
            repo_name = repo_info["name"]
            default_branch = repo_info["default_branch"]
            local_result = {"scanned": False, "findings": [], "error": None, "repo_name": repo_name}
            try:
                scan_result = self._scan_repository(repo_name, default_branch)
                local_result.update(scan_result)
            except Exception as e:
                self.log(f"Unexpected error scanning {repo_name}: {e}", "ERROR")
                local_result["error"] = str(e)
            return local_result

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_scan_single, repo_info): repo_info for repo_info in repositories}
            for future in as_completed(futures):
                scan_result = future.result()
                repo_name = scan_result["repo_name"]
                with scan_lock:
                    if scan_result["scanned"]:
                        results["scanned"] += 1
                        if scan_result["findings"]:
                            results["total_findings"] += len(scan_result["findings"])
                            results["repositories_with_findings"].append({
                                "repository": repo_name,
                                "default_branch": scan_result.get("default_branch", "main"),
                                "findings": scan_result["findings"],
                            })
                    else:
                        results["failed"] += 1
                        if scan_result["error"]:
                            results["scan_errors"].append(
                                {"repository": repo_name, "error": scan_result["error"]}
                            )

        self.log(
            f"Scan completed: {results['scanned']} scanned, "
            f"{results['failed']} failed, {results['total_findings']} findings"
        )
        self._send_notification(results)
        return results

    def _get_all_repositories(self) -> list[dict[str, str]]:
        """Combine allowlist repos with all repos owned by target_owner."""
        try:
            repo_names = self.get_allowed_repositories()
            repos = []
            for repo_name in repo_names:
                try:
                    r = self.github_client.get_repo(repo_name)
                    repos.append({"name": repo_name, "default_branch": r.default_branch})
                except Exception as e:
                    self.log(f"Error fetching repo {repo_name}: {e}", "WARNING")

            self.log(f"Found {len(repos)} repositories to scan for {self.target_owner}")
            return repos
        except Exception as e:
            self.log(f"Error fetching repositories: {e}", "ERROR")
            return []

    def _get_commit_author(self, repo_name: str, commit_sha: str) -> str:
        """Resolve commit SHA to GitHub username, with caching."""
        if not commit_sha:
            return "unknown"
        cache_key = f"{repo_name}:{commit_sha}"
        if cache_key in self._commit_author_cache:
            return self._commit_author_cache[cache_key]
        try:
            repo = self.github_client.g.get_repo(repo_name)
            commit = repo.get_commit(commit_sha)
            author_login = (
                commit.author.login if (commit.author and commit.author.login) else "unknown"
            )
        except Exception as e:
            self.log(f"Error fetching commit author for {commit_sha}: {e}", "WARNING")
            author_login = "unknown"
        self._commit_author_cache[cache_key] = author_login
        return author_login

    # ------------------------------------------------------------------
    # Delegated notification helpers
    # ------------------------------------------------------------------

    def _send_notification(self, results: dict[str, Any]) -> None:
        build_and_send_report(results, self.telegram, self.target_owner, self._get_commit_author)

    def _send_error_notification(self, error_message: str) -> None:
        send_error_notification(self.telegram, self.target_owner, error_message)
