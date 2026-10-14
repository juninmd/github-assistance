from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.agents.orchestration import AgentOrchestrator, create_default_orchestrator
from src.agents.registry import AGENTS_WITH_AI
from src.config.settings import Settings
from src.utils.logger import get_logger

_log = get_logger("batch-runner")

_MAX_PARALLEL_WORKERS = 10

_ENABLED_ATTRS: dict[str, str] = {
    "product-manager": "enable_product_manager",
    "interface-developer": "enable_interface_developer",
    "senior-developer": "enable_senior_developer",
    "pr-assistant": "enable_pr_assistant",
    "security-scanner": "enable_security_scanner",
    "ci-health": "enable_ci_health",
    "pr-sla": "enable_pr_sla",
    "jules-tracker": "enable_jules_tracker",
    "secret-remover": "enable_secret_remover",
    "project-creator": "enable_project_creator",
    "branch-cleaner": "enable_branch_cleaner",
    "intelligence-standardizer": "enable_intelligence_standardizer",
    "readme-curator": "enable_readme_curator",
}

_ALWAYS_ENABLED = {"conflict-resolver", "code-reviewer"}


def _batches(agents: list[str]) -> list[list[str]]:
    """Split agents into dependency-respecting batches (no empty batches)."""
    if not agents:
        return []
    orchestrator = create_default_orchestrator()
    return orchestrator.get_parallel_batches(agents)


def _is_failure(result: dict[str, Any]) -> bool:
    return bool(result.get("error")) or result.get("status") in ("failed", "blocked")


def _blocked_dependencies(
    orchestrator: AgentOrchestrator, agent: str, succeeded: set[str]
) -> list[str]:
    deps = (
        orchestrator.dependencies[agent].depends_on
        if agent in orchestrator.dependencies
        else []
    )
    return [dep for dep in deps if dep not in succeeded]


def run_all(
    settings: Settings, provider: str | None = None, model: str | None = None
) -> dict[str, Any]:
    """Run enabled agents in batches; dependents only run after real success."""
    from src.run_agent import run_agent

    enabled_agents = [
        name
        for name, attr in _ENABLED_ATTRS.items()
        if getattr(settings, attr) and (name not in AGENTS_WITH_AI or settings.enable_ai)
    ]
    enabled_agents.extend(a for a in _ALWAYS_ENABLED if a not in AGENTS_WITH_AI or settings.enable_ai)
    orchestrator = create_default_orchestrator()
    try:
        batches = _batches(enabled_agents)
    except ValueError as e:
        return {"error": str(e), "status": "failed"}

    all_results: dict[str, Any] = {}
    succeeded: set[str] = set()
    for batch_idx, batch in enumerate(batches):
        print(f"\n{'=' * 60}")
        print(f"Batch {batch_idx + 1}/{len(batches)}: {', '.join(batch)}")
        print(f"{'='*60}")
        with ThreadPoolExecutor(max_workers=min(len(batch), _MAX_PARALLEL_WORKERS)) as executor:
            futures = {}
            for name in batch:
                missing = _blocked_dependencies(orchestrator, name, succeeded)
                if missing:
                    all_results[name] = {
                        "status": "blocked",
                        "error": f"dependency failed: {', '.join(missing)}",
                    }
                    _log.error(f"Agent {name} blocked by failed dependency {missing}")
                    continue
                futures[executor.submit(run_agent, name, settings, provider, model)] = name
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = {"error": "agent execution failed"}
                    _log.error(f"Agent {name} failed")
                all_results[name] = result
                if not _is_failure(result):
                    succeeded.add(name)
    return all_results
