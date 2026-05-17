"""Batch execution of multiple agents in parallel."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.agents.orchestration import create_default_orchestrator
from src.agents.registry import AGENTS_WITH_AI
from src.config.settings import Settings

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
}


def run_all(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Run all enabled agents in parallel batches respecting dependencies."""
    from src.run_agent import run_agent
    all_results: dict[str, Any] = {}
    enabled_agents = [
        name for name, attr in _ENABLED_ATTRS.items()
        if getattr(settings, attr)
        and (name not in AGENTS_WITH_AI or settings.enable_ai)
    ]
    always_enabled = ["conflict-resolver", "code-reviewer"]
    enabled_agents.extend(a for a in always_enabled if a not in AGENTS_WITH_AI or settings.enable_ai)
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
