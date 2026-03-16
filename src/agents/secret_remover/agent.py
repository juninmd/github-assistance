"""
Secret Remover Agent — reads security scanner results, classifies each finding
with AI, then creates Jules sessions to remediate real secrets or add allowlist
rules for false positives.
"""
import glob
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.agents.base_agent import BaseAgent
from src.agents.secret_remover.ai_analyzer import analyze_finding
from src.agents.secret_remover.telegram_summary import (
    build_finding_message,
    get_finding_buttons,
    send_error_notification,
)
from src.ai_client import get_ai_client

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

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

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

        results: dict[str, Any] = {
            "total_repos_processed": len(repos),
            "actions_taken": actions_taken,
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
        }
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_latest_results(self) -> dict[str, Any] | None:
        """Return the content of the most recent security-scanner result file.

        The agent may be invoked from a different current working directory, so
        we search in multiple candidate locations:
        1) Current working directory
        2) Repository root (relative to this file)
        3) Optional directory from RESULTS_DIR env var
        """

        candidates = []
        env_dir = os.getenv("RESULTS_DIR")
        if env_dir:
            candidates.append(Path(env_dir))
        candidates.append(Path.cwd())
        # Project root is assumed to be 3 levels above this file (src/agents/<agent>)
        candidates.append(Path(__file__).resolve().parents[3])

        all_files = []
        for base in candidates:
            try:
                pattern = str(base / _RESULTS_GLOB)
                self.log(f"Searching for results in: {pattern}")
                all_files.extend(glob.glob(pattern))
            except Exception as e:
                self.log(f"Error searching for results in {base}: {e}", "WARNING")

        if not all_files:
            return None

        # Prefer the most recent file, but skip any that are malformed.
        for candidate in sorted(set(all_files), reverse=True):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict):
                    self.log(f"Ignoring invalid scanner result (not a dict): {candidate}", "WARNING")
                    continue
                if "repositories_with_findings" not in data:
                    self.log(f"Ignoring invalid scanner result (missing key): {candidate}", "WARNING")
                    continue
                return data
            except json.JSONDecodeError as exc:
                self.log(f"Ignoring malformed JSON in {candidate}: {exc}", "WARNING")
            except Exception as exc:
                self.log(f"Error reading scanner result {candidate}: {exc}", "WARNING")

        return None

    def _process_repo(
        self, repo_name: str, findings: list[dict], default_branch: str
    ) -> dict[str, Any]:
        """Classify findings for one repo and remediate secrets locally."""
        self.log(f"Analysing {len(findings)} finding(s) for {repo_name}")

        ignored_count = 0
        removed_count = 0
        actions = []

        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN not available for local remediation")

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
            clone_dir = os.path.join(temp_dir, "repo")

            self.log(f"Cloning {repo_name} for remediation...")
            subprocess.run(
                ["git", "clone", repo_url, clone_dir],
                check=True, capture_output=True, text=True
            )

            for finding in findings:
                decision = analyze_finding(finding, self.ai_client)
                finding["_action"] = decision["action"]
                finding["_reason"] = decision.get("reason", "")

                if decision["action"] == "REMOVE_FROM_HISTORY":
                    try:
                        self._remove_secret_locally(clone_dir, repo_name, finding, default_branch)
                        removed_count += 1
                        actions.append({"finding": finding, "status": "REMOVED"})
                    except Exception as e:
                        self.log(f"Failed to remove secret in {repo_name}: {e}", "ERROR")
                        actions.append({"finding": finding, "status": "ERROR", "error": str(e)})
                else:
                    ignored_count += 1
                    actions.append({"finding": finding, "status": "IGNORED"})

        return {
            "repository": repo_name,
            "ignored": ignored_count,
            "to_remove": removed_count,
            "actions": actions,
        }

    def _remove_secret_locally(self, clone_dir: str, repo_name: str, finding: dict, default_branch: str):
        """Use git-filter-repo to purge a file from history and force-push."""
        file_path = finding["file"]
        full_path = os.path.join(clone_dir, file_path)

        # 1. Capture original line content
        original_line = "N/A"
        try:
            if os.path.exists(full_path):
                with open(full_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    line_idx = finding.get("line", 1) - 1
                    if 0 <= line_idx < len(lines):
                        original_line = lines[line_idx].strip()
        except Exception:
            pass

        # 2. Notify Telegram BEFORE removal (as requested by user)
        file_url = f"https://github.com/{repo_name}/blob/{default_branch}/{quote(file_path)}"
        # Link to the commit where the secret was found
        finding_commit_url = f"https://github.com/{repo_name}/commit/{finding.get('full_commit', '')}"

        msg = build_finding_message(
            repo_name=repo_name,
            finding=finding,
            original_line=original_line,
            modified_line="⏳ [REMOVENDO DO HISTÓRICO AGORA...]",
            telegram=self.telegram
        )
        msg = "🚨 *INICIANDO REMOÇÃO DE SECRET*\n\n" + msg
        buttons = get_finding_buttons(file_url, finding_commit_url)
        self.telegram.send_message(msg, parse_mode="MarkdownV2", reply_markup={"inline_keyboard": buttons})

        # 3. Run git-filter-repo
        # Note: --path expects relative path from repo root
        self.log(f"Running git-filter-repo for {file_path} in {repo_name}")
        subprocess.run(
            ["python", "-m", "git_filter_repo", "--path", file_path, "--invert-paths", "--force"],
            cwd=clone_dir, check=True, capture_output=True, text=True
        )

        # 4. Force push
        self.log(f"Force-pushing changes to {repo_name}...")
        subprocess.run(
            ["git", "push", "origin", "--force", "--all"],
            cwd=clone_dir, check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "push", "origin", "--force", "--tags"],
            cwd=clone_dir, check=True, capture_output=True, text=True
        )

    def _create_allowlist_session(
        self, repo_name: str, findings: list[dict], default_branch: str
    ) -> dict[str, Any] | None:
        """Create a Jules session that adds .gitleaks.toml allowlist entries."""
        entries = "\n".join(
            f'[[allowlist]]\n'
            f'description = "False positive: {f["rule_id"]} in {f["file"]}"\n'
            f'rules = ["{f["rule_id"]}"]\n'
            f'paths = [\'"{f["file"]}"\']'
            for f in findings
        )
        instructions = (
            "Add the following allowlist entries to `.gitleaks.toml` in the "
            "repository root (create the file if it does not exist):\n\n"
            f"{entries}\n\n"
            "Then commit and open a pull request titled "
            "'chore: add gitleaks allowlist entries'."
        )
        try:
            result = self.create_jules_session(
                repository=repo_name,
                instructions=instructions,
                title=f"chore: add gitleaks allowlist ({len(findings)} entries)",
                base_branch=default_branch,
            )
            return {"kind": "IGNORE", "target": f"{len(findings)} findings", "session_id": result.get("id")}
        except Exception as exc:
            self.log(f"Failed to create allowlist session for {repo_name}: {exc}", "WARNING")
            return None

    def _create_removal_session(
        self, repo_name: str, finding: dict, default_branch: str
    ) -> dict[str, Any] | None:
        """Create a Jules session that rewrites history to remove a secret file."""
        file_path = finding["file"]
        instructions = (
            f"This repository has a real secret committed at `{file_path}`.\n\n"
            "Please:\n"
            "1. Install `git-filter-repo` if not available: `pip install git-filter-repo`\n"
            f"2. Run: `git-filter-repo --path '{file_path}' --invert-paths --force`\n"
            "3. Force-push all branches: `git push --force --all`\n"
            "4. Force-push all tags: `git push --force --tags`\n"
            f"5. Add `{file_path}` to `.gitignore` to prevent re-commit\n"
            "6. Open a pull request documenting the remediation.\n\n"
            "⚠️ Warn in the PR description that all collaborators must re-clone."
        )
        try:
            result = self.create_jules_session(
                repository=repo_name,
                instructions=instructions,
                title=f"security: remove secret from history ({os.path.basename(file_path)})",
                base_branch=default_branch,
            )
            return {"kind": "REMOVE", "target": file_path, "session_id": result.get("id")}
        except Exception as exc:
            self.log(f"Failed to create removal session for {repo_name}/{file_path}: {exc}", "WARNING")
            return None
