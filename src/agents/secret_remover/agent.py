"""
Secret Remover Agent — reads security scanner results, classifies each finding
with AI (local Ollama), then remediates real secrets or applies allowlist rules
for false positives directly (no Jules).
"""
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.secret_remover import utils
from src.agents.secret_remover.ai_analyzer import analyze_finding
from src.agents.secret_remover.telegram_summary import (
    send_error_notification,
    send_finding_notification,
)
from src.ai_client import get_ai_client

_RESULTS_GLOB = "results/security-scanner_*.json"
_MAX_FINDINGS_PER_RUN = 300  # guard against runaway AI calls
_DEFAULT_AI_PROVIDER = "ollama"
_DEFAULT_AI_MODEL = "qwen3:1.7b"


class SecretRemoverAgent(BaseAgent):
    """
    Reads the most recent Security Scanner output, classifies every finding via
    AI (Ollama), and remediates directly without Jules.
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
        provider = ai_provider or os.getenv("SECRET_REMOVER_AI_PROVIDER", _DEFAULT_AI_PROVIDER)
        model = ai_model or os.getenv("SECRET_REMOVER_AI_MODEL", _DEFAULT_AI_MODEL)
        self.ai_client = get_ai_client(provider, model=model, **(ai_config or {}))

    def _find_latest_results(self) -> dict[str, Any] | None:
        return utils.find_latest_results(self.log, _RESULTS_GLOB)

    def run(self) -> dict[str, Any]:
        """Load latest scanner results, classify findings, remediate."""
        self.log("Starting Secret Remover workflow")

        latest = self._find_latest_results()
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

        return {
            "total_repos_processed": len(repos),
            "actions_taken": actions_taken,
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
        }

    def _process_repo(
        self, repo_name: str, findings: list[dict], default_branch: str
    ) -> dict[str, Any]:
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

            for finding in findings:
                finding_copy = dict(finding)
                finding_copy["redacted_context"] = self._build_redacted_context(
                    clone_dir, finding_copy
                )
                original_line = utils.get_original_line(clone_dir, finding_copy)
                decision = analyze_finding(finding_copy, self.ai_client)
                finding_copy["_action"] = decision["action"]
                finding_copy["_reason"] = decision.get("reason", "")

                commit_sha = finding_copy.get("commit", "HEAD")
                file_path = finding_copy.get("file", "")
                line = int(finding_copy.get("line", 0) or 0)

                commit_url = utils.build_commit_url(repo_name, commit_sha)
                file_line_url = utils.build_file_line_url(repo_name, commit_sha, file_path, line)
                repo_url_pub = utils.build_repo_url(repo_name)

                if decision["action"] == "REMOVE_FROM_HISTORY":
                    success = self._create_removal_session(repo_name, finding_copy, clone_dir)
                    actions.append({
                        "finding": finding_copy,
                        "status": "REMOVED" if success else "ERROR",
                    })
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
                    commit_url=commit_url,
                    file_line_url=file_line_url,
                    repo_url=repo_url_pub,
                )

            if ignored_findings:
                success = self._create_allowlist_session(
                    repo_name, ignored_findings, default_branch, clone_dir, token
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

    def _build_redacted_context(self, clone_dir: str, finding: dict[str, Any]) -> str:
        return utils.build_redacted_context(clone_dir, finding)

    def _create_allowlist_session(
        self,
        repo_name: str,
        findings: list[dict],
        default_branch: str,
        clone_dir: str = "",
        token: str = "",
    ) -> bool:
        """Apply false-positive allowlist entries locally (no Jules)."""
        if not clone_dir:
            self.log(f"Cannot apply allowlist for {repo_name}: clone_dir missing", "WARNING")
            return False
        try:
            return utils.apply_allowlist_locally(
                repo_name=repo_name,
                findings=findings,
                clone_dir=clone_dir,
                token=token,
                log_func=self.log,
                default_branch=default_branch,
            )
        except Exception as exc:
            self.log(f"Failed to apply allowlist for {repo_name}: {exc}", "WARNING")
            return False

    def _create_removal_session(
        self, repo_name: str, finding: dict, clone_dir: str = ""
    ) -> bool:
        """Remove a real secret from git history locally (no Jules)."""
        if not clone_dir:
            self.log(f"Cannot remove secret for {repo_name}: clone_dir missing", "WARNING")
            return False
        try:
            return utils.remove_secret_from_history(
                repo_name=repo_name,
                finding=finding,
                clone_dir=clone_dir,
                log_func=self.log,
            )
        except Exception as exc:
            self.log(f"Failed to remove secret for {repo_name}: {exc}", "WARNING")
            return False
