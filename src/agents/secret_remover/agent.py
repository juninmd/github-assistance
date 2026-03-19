"""
Secret Remover Agent — reads security scanner results, classifies each finding
with AI, then creates Jules sessions to remediate real secrets or add allowlist
rules for false positives.
"""
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.secret_remover.ai_analyzer import analyze_finding
from src.agents.secret_remover.telegram_summary import send_error_notification
from src.ai_client import get_ai_client
from src.agents.secret_remover import utils

_RESULTS_GLOB = "results/security-scanner_*.json"
_MAX_FINDINGS_PER_RUN = 300  # guard against runaway AI calls


class SecretRemoverAgent(BaseAgent):
    """
    Reads the most recent Security Scanner output, classifies every finding via
    AI, and delegates remediation to Jules.
    """

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        target_owner: str = "juninmd",
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(
            *args, name="secret_remover", enforce_repository_allowlist=False, **kwargs
        )
        self.target_owner = target_owner
        self.ai_client = get_ai_client(
            provider=ai_provider or "gemini",
            model=ai_model or "gemini-2.5-flash",
            **(ai_config or {}),
        )

    def run(self) -> dict[str, Any]:
        """Load latest scanner results, classify findings, remediate."""
        self.log("Starting Secret Remover workflow")

        latest = utils.find_latest_results(self.log, _RESULTS_GLOB)
        if not latest:
            msg = "No security scanner results found in results/."
            self.log(msg, "ERROR")
            send_error_notification(self.telegram, self.target_owner, msg)
            return {"error": msg}

        repos = latest.get("repositories_with_findings", [])
        self.log(f"Processing {len(repos)} repositories with findings")

        actions_taken: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        processed_count = 0

        for repo_data in repos:
            if processed_count >= _MAX_FINDINGS_PER_RUN:
                self.log(f"Reached max findings limit ({_MAX_FINDINGS_PER_RUN}), stopping")
                break
            repo_name = repo_data["repository"]
            findings = repo_data["findings"]
            default_branch = repo_data.get("default_branch", "main")
            remaining = _MAX_FINDINGS_PER_RUN - processed_count
            findings = findings[:remaining]
            processed_count += len(findings)
            try:
                result = self._process_repo(repo_name, findings, default_branch)
                actions_taken.append(result)
            except Exception as exc:
                self.log(f"Error processing {repo_name}: {exc}", "ERROR")
                errors.append({"repository": repo_name, "error": str(exc)})

        results: dict[str, Any] = {
            "total_repos_processed": len(repos),
            "actions_taken": actions_taken,
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
        }
        return results

    def _process_repo(
        self, repo_name: str, findings: list[dict], default_branch: str
    ) -> dict[str, Any]:
        """Classify findings for one repo and create remediation sessions."""
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
                check=True, capture_output=True, text=True
            )

            for finding in findings:
                finding_copy = dict(finding)
                finding_copy["redacted_context"] = utils.build_redacted_context(
                    clone_dir, finding_copy
                )
                decision = analyze_finding(finding_copy, self.ai_client)
                finding_copy["_action"] = decision["action"]
                finding_copy["_reason"] = decision.get("reason", "")

                if decision["action"] == "REMOVE_FROM_HISTORY":
                    session = utils.create_removal_session(
                        repo_name, finding_copy, default_branch,
                        self.create_jules_session, self.log
                    )
                    if session is not None:
                        removed_count += 1
                        actions.append({
                            "finding": finding_copy,
                            "status": "SESSION_CREATED",
                            "session": session,
                        })
                    else:
                        actions.append({
                            "finding": finding_copy,
                            "status": "ERROR",
                            "error": "Failed to create removal session",
                        })
                else:
                    ignored_count += 1
                    ignored_findings.append(finding_copy)
                    actions.append({"finding": finding_copy, "status": "IGNORED"})

            if ignored_findings:
                allowlist_session = utils.create_allowlist_session(
                    repo_name, ignored_findings, default_branch,
                    self.create_jules_session, self.log
                )
                actions.append({
                    "status": (
                        "ALLOWLIST_SESSION_CREATED"
                        if allowlist_session is not None
                        else "ALLOWLIST_SESSION_ERROR"
                    ),
                    "findings_count": len(ignored_findings),
                    "session": allowlist_session,
                })

        return {
            "repository": repo_name,
            "ignored": ignored_count,
            "to_remove": removed_count,
            "actions": actions,
        }
