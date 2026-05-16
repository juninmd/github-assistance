"""
Secret Remover Agent — reads security scanner results, classifies each finding
with AI (local Ollama), then remediates real secrets or applies allowlist rules
for false positives directly (no Jules).
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.secret_remover import utils
from src.agents.secret_remover.processor import FindingProcessor
from src.agents.secret_remover.telegram_summary import send_error_notification
from src.ai import get_ai_client

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
        jules_client: Any,
        github_client: Any,
        allowlist: Any,
        *args,
        target_owner: str = "juninmd",
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(
            jules_client,
            github_client,
            allowlist,
            *args,
            name="secret_remover",
            enforce_repository_allowlist=False,
            **kwargs,
        )
        self.target_owner = target_owner
        provider = ai_provider or os.getenv("SECRET_REMOVER_AI_PROVIDER", _DEFAULT_AI_PROVIDER)
        model = ai_model or os.getenv("SECRET_REMOVER_AI_MODEL", _DEFAULT_AI_MODEL)
        self.ai_client = get_ai_client(provider, model=model, **(ai_config or {}))
        self.processor = FindingProcessor(self.ai_client, self.telegram, self.log)

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

        # Limit findings per run before submitting
        repo_batches = []
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
            repo_batches.append((repo_name, findings, default_branch))

        # Process repos in parallel since findings are independent per repo
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(self.processor.process_repo, name, fings, branch): name for name, fings, branch in repo_batches}
            for future in as_completed(futures):
                repo_name = futures[future]
                try:
                    result = future.result()
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
