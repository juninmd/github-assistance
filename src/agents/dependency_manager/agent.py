"""Dependency Manager Agent - keeps repository dependencies fresh and secure.

Detects the ecosystems a repo uses, then delegates the actual upgrade to
opencode (AI): security/CVE fixes first, then patch/minor bumps, always with
the lockfile updated and tests run. Opens a single grouped pull request.
"""

import os
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.dependency_manager.detect import Ecosystem, detect_ecosystems, root_filenames


def dependency_dry_run() -> bool:
    """When true, detection runs but no opencode task/PR is created."""
    return os.getenv("DEPENDENCY_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}


class DependencyManagerAgent(BaseAgent):
    """Detects dependency ecosystems and opens safe upgrade PRs via opencode."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, name="dependency_manager", enforce_repository_allowlist=True, **kwargs
        )

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        self.check_rate_limit()
        self.log("Starting Dependency Manager workflow")
        results: dict[str, Any] = {"processed": [], "skipped": [], "failed": []}

        for repo_name in self.get_allowed_repositories():
            try:
                self._process_repository(repo_name, results)
            except Exception as e:
                self.log(f"Failed to process {repo_name}: {e}", "ERROR")
                results["failed"].append({"repository": repo_name, "error": str(e)})

        self._send_summary(results)
        return results

    def _process_repository(self, repo_name: str, results: dict[str, Any]) -> None:
        repo = self.github_client.get_repo(repo_name)
        ecosystems = self._detect(repo)
        if not ecosystems:
            self.log(f"No dependencies detected in {repo_name}")
            results["skipped"].append({"repository": repo_name, "reason": "no_dependencies"})
            return

        names = ", ".join(e.name for e in ecosystems)
        if dependency_dry_run():
            self.log(f"[DRY-RUN] {repo_name}: would update dependencies ({names})")
            results["processed"].append(
                {
                    "repository": repo_name,
                    "ecosystems": [e.name for e in ecosystems],
                    "pr_url": None,
                    "status": "dry_run",
                }
            )
            return

        self.log(f"{repo_name}: updating dependencies ({names})")
        oc_result = self.create_opencode_task(
            repository=repo_name,
            instructions=self._build_instructions(ecosystems),
            title=f"Update dependencies for {repo.name}",
            base_branch=repo.default_branch,
        )
        results["processed"].append(
            {
                "repository": repo_name,
                "ecosystems": [e.name for e in ecosystems],
                "pr_url": oc_result.get("task_url"),
                "status": oc_result.get("status"),
            }
        )

    def _detect(self, repo: Any) -> list[Ecosystem]:
        try:
            tree = repo.get_git_tree(repo.default_branch, recursive=True)
            files = [item.path for item in tree.tree]
        except Exception as e:
            self.log(f"Could not read tree for {repo.full_name}: {e}", "WARNING")
            return []
        return detect_ecosystems(root_filenames(files))

    @staticmethod
    def _build_instructions(ecosystems: list[Ecosystem]) -> str:
        lines = [
            "Atualize as dependências deste repositório com segurança, priorizando "
            "correções de segurança. Use a IA (opencode) para decidir e aplicar.",
            "",
            "Ecossistemas detectados:",
            *(f"- {e.summary} | auditoria: {e.audit_hint} | desatualizadas: {e.outdated_hint}"
              for e in ecosystems),
            "",
            "Regras:",
            "1. Segurança primeiro: rode a auditoria e corrija vulnerabilidades (CVE) "
            "antes de qualquer bump não essencial.",
            "2. Liste o que está desatualizado e aplique bumps de patch/minor.",
            "3. NÃO aplique majors sem checar breaking changes; se houver, deixe "
            "documentado e fora deste PR.",
            "4. Atualize o lockfile e rode a suíte de testes; corrija o que quebrar.",
            "5. Mudanças mínimas e verificáveis; não refatore código não relacionado.",
            "",
            "Abra UM pull request agrupado, com resumo no corpo: dependências "
            "atualizadas, CVEs corrigidas e breaking changes evitadas.",
        ]
        return "\n".join(lines)

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        processed = results.get("processed", [])
        skipped = results.get("skipped", [])
        failed = results.get("failed", [])
        lines = [
            "📦 <b>DEPENDENCY MANAGER AGENT</b>",
            "──────────────────────",
            f"✅ <b>PRs abertos:</b> <code>{len(processed)}</code>",
            f"⏭️ <b>Pulados:</b> <code>{len(skipped)}</code>  ❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for item in processed[:5]:
            repo = esc(item["repository"])
            pr_url = item.get("pr_url")
            ecos = esc(", ".join(item.get("ecosystems", [])))
            if pr_url:
                lines.append(f'  └ <a href="{esc(pr_url)}">{repo}</a> ({ecos})')
            else:
                lines.append(f"  └ <code>{repo}</code> ({ecos})")
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
