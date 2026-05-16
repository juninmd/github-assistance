"""Batch execution of multiple agents in parallel."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.agents.orchestration import create_default_orchestrator
from src.agents.registry import AGENTS_WITH_AI
from src.config.settings import Settings


def run_all(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Run all enabled agents in parallel batches respecting dependencies."""
    from src.run_agent import run_agent
    all_results: dict[str, Any] = {}
    enabled_map = {
        "product-manager": settings.enable_product_manager,
        "interface-developer": settings.enable_interface_developer,
        "senior-developer": settings.enable_senior_developer,
        "pr-assistant": settings.enable_pr_assistant,
        "security-scanner": settings.enable_security_scanner,
        "ci-health": settings.enable_ci_health,
        "pr-sla": settings.enable_pr_sla,
        "jules-tracker": settings.enable_jules_tracker,
        "secret-remover": settings.enable_secret_remover,
        "project-creator": settings.enable_project_creator,
        "branch-cleaner": settings.enable_branch_cleaner,
        "intelligence-standardizer": settings.enable_intelligence_standardizer,
        "conflict-resolver": True,
        "code-reviewer": True,
    }
    enabled_agents = [
        name for name, enabled in enabled_map.items()
        if enabled and (name not in AGENTS_WITH_AI or settings.enable_ai)
    ]
    orchestrator = create_default_orchestrator()
    batches = orchestrator.get_parallel_batches(enabled_agents)

    for batch_idx, batch in enumerate(batches):
        print(f"\n{'='*60}")
        print(f"Batch {batch_idx + 1}/{len(batches)}: {', '.join(batch)}")
        print(f"{'='*60}")
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {executor.submit(run_agent, name, settings, provider, model): name for name in batch}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    all_results[name] = future.result()
                except Exception as e:
                    print(f"Error running {name}: {e}")
                    all_results[name] = {"error": str(e)}
    return all_results