"""Logic for processing findings in a repository for Secret Remover Agent."""
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.agents.secret_remover import git_utils, utils
from src.agents.secret_remover.ai_analyzer import analyze_finding
from src.agents.secret_remover.telegram_summary import send_finding_notification


def _classify_finding(finding: dict, clone_dir: str, repo_name: str, ai_client) -> dict[str, Any]:
    """Classify a single finding using AI (runs in thread pool)."""
    finding_copy = dict(finding)
    finding_copy["redacted_context"] = utils.build_redacted_context(clone_dir, finding_copy)
    original_line = utils.get_original_line(clone_dir, finding_copy)
    decision = analyze_finding(finding_copy, ai_client)
    finding_copy["_action"] = decision["action"]
    finding_copy["_reason"] = decision.get("reason", "")

    commit_sha = finding_copy.get("commit", "HEAD")
    file_path = finding_copy.get("file", "")
    line = int(finding_copy.get("line", 0) or 0)

    return {
        "finding": finding_copy,
        "decision": decision,
        "original_line": original_line,
        "commit_sha": commit_sha,
        "file_path": file_path,
        "line": line,
        "commit_url": utils.build_commit_url(repo_name, commit_sha),
        "file_line_url": utils.build_file_line_url(repo_name, commit_sha, file_path, line),
        "repo_url": utils.build_repo_url(repo_name),
    }


class FindingProcessor:
    """Encapsulates the logic for processing findings in a repository."""

    def __init__(self, ai_client, telegram, log_func):
        self.ai_client = ai_client
        self.telegram = telegram
        self.log = log_func

    def process_repo(self, repo_name: str, findings: list[dict], default_branch: str) -> dict[str, Any]:
        """Classify findings for one repo and remediate directly."""
        self.log(f"Analysing {len(findings)} finding(s) for {repo_name}")

        ignored_count = 0
        removed_count = 0
        actions = []
        ignored_findings: list[dict[str, Any]] = []

        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN not available for repository analysis")

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
            clone_dir = os.path.join(temp_dir, "repo")

            self.log(f"Cloning {repo_name} for analysis...")
            subprocess.run(
                ["git", "clone", "--single-branch", repo_url, clone_dir],
                check=True, capture_output=True, text=True,
            )

            classified: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=min(5, len(findings) or 1)) as executor:
                futures = {
                    executor.submit(_classify_finding, finding, clone_dir, repo_name, self.ai_client): i
                    for i, finding in enumerate(findings)
                }
                for future in as_completed(futures):
                    try:
                        classified.append(future.result())
                    except Exception as e:
                        self.log(f"Error classifying finding: {e}", "ERROR")

            for result in classified:
                finding_copy = result["finding"]
                decision = result["decision"]
                original_line = result["original_line"]

                if decision["action"] == "REMOVE_FROM_HISTORY":
                    success = git_utils.remove_secret_from_history(
                        repo_name, finding_copy, clone_dir, self.log
                    )
                    actions.append({"finding": finding_copy, "status": "REMOVED" if success else "ERROR"})
                    if success:
                        removed_count += 1
                else:
                    ignored_count += 1
                    ignored_findings.append(finding_copy)
                    actions.append({"finding": finding_copy, "status": "IGNORED"})

                send_finding_notification(
                    telegram=self.telegram,
                    repo_name=repo_name,
                    finding=finding_copy,
                    action=decision["action"],
                    original_line=original_line,
                    commit_url=result["commit_url"],
                    file_line_url=result["file_line_url"],
                    repo_url=result["repo_url"],
                )

            if ignored_findings:
                success = git_utils.apply_allowlist_locally(
                    repo_name, ignored_findings, clone_dir, token, self.log, default_branch
                )
                actions.append({
                    "status": "ALLOWLIST_APPLIED" if success else "ALLOWLIST_ERROR",
                    "findings_count": len(ignored_findings),
                })

        return {
            "repository": repo_name,
            "ignored": ignored_count,
            "to_remove": removed_count,
            "actions": actions,
        }
