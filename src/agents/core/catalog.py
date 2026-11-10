"""Agent catalog: the single source of truth for every agent in the fleet.

Adding an agent means adding one ``AgentSpec`` here (plus its package under
``src/agents/<name>/``). The registry, the batch runner, the orchestrator, the
``Settings`` toggles, the console entry points, the health checks and the
dashboard all derive from this table, so nothing can drift out of sync.

This module is pure data and must stay import-free of the rest of ``src``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentPriority(Enum):
    """Execution priority (lower value runs first)."""

    CRITICAL = 1  # security
    HIGH = 2  # PR / CI blockers
    MEDIUM = 3
    LOW = 4


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Static description of one agent."""

    name: str  # CLI name, kebab-case: `run-agent <name>`
    class_name: str
    emoji: str
    summary: str  # user-facing (dashboard), in pt-BR like the Telegram reports
    priority: AgentPriority = AgentPriority.MEDIUM
    toggle_env: str | None = None  # `*_ENABLED` env var; None = no toggle
    requires_ai: bool = False  # refuses to start when ENABLE_AI=false
    uses_jules: bool = False
    notifies_telegram: bool = False
    accepts_pr_ref: bool = False  # supports `--pr owner/repo#N`
    depends_on: tuple[str, ...] = ()
    in_batch: bool = True  # part of `run-agent all`

    @property
    def package(self) -> str:
        """Python package name: ``src/agents/<package>/``."""
        return self.name.replace("-", "_")

    @property
    def import_path(self) -> str:
        return f"src.agents.{self.package}.agent:{self.class_name}"

    @property
    def toggle_attr(self) -> str | None:
        """``Settings`` attribute holding the toggle (``enable_<package>``)."""
        return f"enable_{self.package}" if self.toggle_env else None


_C, _H, _M, _L = (
    AgentPriority.CRITICAL,
    AgentPriority.HIGH,
    AgentPriority.MEDIUM,
    AgentPriority.LOW,
)

AGENT_CATALOG: tuple[AgentSpec, ...] = (
    # --- Security -----------------------------------------------------------
    AgentSpec(
        "security-scanner", "SecurityScannerAgent", "🔒",
        "Gitleaks em todos os repositórios do owner; aplica a política no-cron-workflow",
        _C, "SECURITY_SCANNER_ENABLED", notifies_telegram=True,
    ),
    AgentSpec(
        "secret-remover", "SecretRemoverAgent", "🛡️",
        "Classifica achados com IA e reescreve o histórico git para remover segredos reais",
        _C, "SECRET_REMOVER_ENABLED", requires_ai=True, notifies_telegram=True,
        depends_on=("security-scanner",),
    ),
    # --- Pull requests and CI -----------------------------------------------
    AgentSpec(
        "pr-assistant", "PRAssistantAgent", "🤖",
        "Aplica sugestões de revisão, corrige CI/conflitos e faz squash merge via MergePolicy",
        _H, "PR_ASSISTANT_ENABLED", notifies_telegram=True, accepts_pr_ref=True,
    ),
    AgentSpec(
        "conflict-resolver", "ConflictResolverAgent", "⚔️",
        "Encontra PRs com conflito e resolve com IA de forma segura",
        _H, notifies_telegram=True, accepts_pr_ref=True,
    ),
    AgentSpec(
        "code-reviewer", "CodeReviewerAgent", "👀",
        "Revisa PRs: qualidade, bugs, segurança e performance",
        _H, "CODE_REVIEWER_ENABLED", requires_ai=True, notifies_telegram=True,
        accepts_pr_ref=True,
    ),
    AgentSpec(
        "ci-health", "CIHealthAgent", "⚕️",
        "Monitora pipelines, detecta falhas/flaky e dispara remediação",
        _H, "CI_HEALTH_ENABLED", notifies_telegram=True,
    ),
    AgentSpec(
        "pr-sla", "PRSLAAgent", "⏱️",
        "Acompanha idade e tempo de revisão de PRs; alerta sobre PRs paradas",
        _L, "PR_SLA_ENABLED",
    ),
    # --- Development and documentation --------------------------------------
    AgentSpec(
        "senior-developer", "SeniorDeveloperAgent", "🏗️",
        "Segurança, CI/CD, dívida técnica, modernização e entrega do roadmap",
        _M, "DEV_AGENT_ENABLED", requires_ai=True, uses_jules=True, notifies_telegram=True,
    ),
    AgentSpec(
        "dependency-manager", "DependencyManagerAgent", "📦",
        "CVEs primeiro, depois patch/minor seguros, em um único PR agrupado",
        _M, "DEPENDENCY_MANAGER_ENABLED", notifies_telegram=True,
    ),
    AgentSpec(
        "readme-curator", "ReadmeCuratorAgent", "📚",
        "Reescreve READMEs ausentes, antigos ou com nota baixa em todo o portfólio",
        _M, "README_CURATOR_ENABLED", requires_ai=True, notifies_telegram=True,
    ),
    AgentSpec(
        "intelligence-standardizer", "IntelligenceStandardizerAgent", "🧬",
        "Garante AGENTS.md e .agents/ consistentes nos repositórios recentes",
        _M, "INTELLIGENCE_AGENT_ENABLED", requires_ai=True, uses_jules=True,
        notifies_telegram=True,
    ),
    AgentSpec(
        "product-manager", "ProductManagerAgent", "📋",
        "Mantém backlog, roadmap e documentação de produto",
        _L, "PM_AGENT_ENABLED", requires_ai=True, uses_jules=True,
    ),
    AgentSpec(
        "interface-developer", "InterfaceDeveloperAgent", "🎨",
        "UI/UX, acessibilidade e responsividade via tarefas Jules",
        _L, "UI_AGENT_ENABLED", requires_ai=True, uses_jules=True,
    ),
    AgentSpec(
        "project-creator", "ProjectCreatorAgent", "🚀",
        "Gera ideia ancorada no portfólio, cria o repositório e inicia o Jules",
        _L, "PROJECT_CREATOR_ENABLED", requires_ai=True, uses_jules=True,
    ),
    # --- Hygiene and Jules --------------------------------------------------
    AgentSpec(
        "branch-cleaner", "BranchCleanerAgent", "🧹",
        "Remove branches mergeadas (nunca a principal nem as que têm PR aberto)",
        _M, "BRANCH_CLEANER_ENABLED", notifies_telegram=True,
    ),
    AgentSpec(
        "jules-tracker", "JulesTrackerAgent", "🔍",
        "Monitora sessões Jules; responde perguntas e aprova ou ajusta planos",
        _M, "JULES_TRACKER_ENABLED", uses_jules=True,
    ),
    AgentSpec(
        "jules-cleaner", "JulesCleanerAgent", "🗑️",
        "Apaga sessões Jules mais velhas que JULES_CLEANER_MAX_AGE_DAYS",
        _M, uses_jules=True, notifies_telegram=True, in_batch=False,
    ),
)

AGENTS_BY_NAME: dict[str, AgentSpec] = {spec.name: spec for spec in AGENT_CATALOG}


def agent_names(
    *,
    requires_ai: bool | None = None,
    uses_jules: bool | None = None,
    notifies_telegram: bool | None = None,
    accepts_pr_ref: bool | None = None,
) -> set[str]:
    """Names of the agents matching every given capability filter."""
    filters = {
        "requires_ai": requires_ai,
        "uses_jules": uses_jules,
        "notifies_telegram": notifies_telegram,
        "accepts_pr_ref": accepts_pr_ref,
    }
    return {
        spec.name
        for spec in AGENT_CATALOG
        if all(getattr(spec, key) is want for key, want in filters.items() if want is not None)
    }
