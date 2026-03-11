"""
Central runner for all AI agents.
Usage: uv run run-agent <agent-name> [--pr owner/repo#number] [--ai-provider gemini] [--ai-model gemini-2.5-flash]
"""
import json
import os
import sys
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.ci_health.agent import CIHealthAgent
from src.agents.interface_developer.agent import InterfaceDeveloperAgent
from src.agents.jules_tracker.agent import JulesTrackerAgent
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.agents.pr_sla.agent import PRSLAAgent
from src.agents.product_manager.agent import ProductManagerAgent
from src.agents.security_scanner.agent import SecurityScannerAgent
from src.agents.senior_developer.agent import SeniorDeveloperAgent
from src.config.repository_allowlist import RepositoryAllowlist
from src.config.settings import Settings
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier


def _create_base_deps(settings: Settings) -> dict[str, Any]:
    """Create the shared dependencies every agent needs."""
    return {
        "github_client": GithubClient(settings.github_token),
        "jules_client": JulesClient(settings.jules_api_key),
        "allowlist": RepositoryAllowlist(settings.repository_allowlist_path),
        "telegram": TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        ),
    }


def _build_ai_config(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Build AI config dict from settings with optional overrides."""
    config: dict[str, Any] = {}
    resolved_provider = provider or settings.ai_provider
    resolved_model = model or settings.ai_model

    # Set default model if only provider is given
    if provider and not model:
        from src.config.settings import DEFAULT_MODELS
        resolved_model = DEFAULT_MODELS.get(resolved_provider, resolved_model)

    if resolved_provider == "gemini":
        config["api_key"] = settings.gemini_api_key
    elif resolved_provider == "openai":
        config["api_key"] = settings.openai_api_key
    elif resolved_provider == "ollama":
        config["base_url"] = settings.ollama_base_url

    return {"ai_provider": resolved_provider, "ai_model": resolved_model, "ai_config": config}


# --- Agent registry -----------------------------------------------------------

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "product-manager": ProductManagerAgent,
    "interface-developer": InterfaceDeveloperAgent,
    "senior-developer": SeniorDeveloperAgent,
    "pr-assistant": PRAssistantAgent,
    "security-scanner": SecurityScannerAgent,
    "ci-health": CIHealthAgent,
    "pr-sla": PRSLAAgent,
    "jules-tracker": JulesTrackerAgent,
}

AGENTS_WITH_AI = {"product-manager", "interface-developer", "senior-developer", "pr-assistant", "jules-tracker"}


def _create_agent(
    agent_name: str,
    settings: Settings,
    provider: str | None = None,
    model: str | None = None,
    pr_ref: str | None = None,
) -> BaseAgent:
    """Instantiate any agent by name with all dependencies."""
    agent_cls = AGENT_REGISTRY[agent_name]
    deps = _create_base_deps(settings)
    kwargs: dict[str, Any] = {**deps}
    kwargs["target_owner"] = settings.github_owner

    if agent_name in AGENTS_WITH_AI:
        if not settings.enable_ai:
            raise PermissionError(f"Agent '{agent_name}' requires AI but ENABLE_AI is false.")
        kwargs.update(_build_ai_config(settings, provider, model))

    if agent_name == "pr-assistant" and pr_ref:
        kwargs["pr_ref"] = pr_ref

    return agent_cls(**kwargs)


# --- Results / reporting -----------------------------------------------------

def save_results(agent_name: str, results: dict[str, Any]) -> None:
    output_dir = os.path.join(os.getcwd(), "results")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"{agent_name}_{timestamp}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to {filename}")


def send_execution_report(telegram: TelegramNotifier, agent_name: str, results: dict[str, Any]) -> None:
    esc = telegram.escape
    lines = [
        "📊 *Relatório de Execução*",
        f"🤖 Agente: `{esc(agent_name)}`",
        f"⏰ {esc(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
    ]
    processed = results.get("processed", results.get("merged", []))
    failed = results.get("failed", [])
    lines.append(f"✅ Processados: *{len(processed) if isinstance(processed, list) else processed}*")
    if failed:
        lines.append(f"❌ Falhas: *{len(failed)}*")
    telegram.send_message("\n".join(lines), parse_mode="MarkdownV2")


# --- CLI entry point ----------------------------------------------------------

def run_agent(agent_name: str, settings: Settings, provider: str | None = None, model: str | None = None, pr_ref: str | None = None) -> dict[str, Any]:
    """Run a single agent and save its results."""
    print(f"\n{'='*60}\nRunning agent: {agent_name}\n{'='*60}")
    agent = _create_agent(agent_name, settings, provider, model, pr_ref)
    results = agent.run()
    save_results(agent_name, results)
    return results


def run_all(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Run all enabled agents sequentially."""
    all_results: dict[str, Any] = {}
    enabled_map = {
        "product-manager": settings.enable_product_manager,
        "interface-developer": settings.enable_interface_developer,
        "senior-developer": settings.enable_senior_developer,
        "pr-assistant": settings.enable_pr_assistant,
        "security-scanner": settings.enable_security_scanner,
        "ci-health": settings.enable_ci_health,
        "release-watcher": settings.enable_release_watcher,
        "dependency-risk": settings.enable_dependency_risk,
        "pr-sla": settings.enable_pr_sla,
        "issue-escalation": settings.enable_issue_escalation,
        "jules-tracker": settings.enable_jules_tracker,
    }
    for name, enabled in enabled_map.items():
        if not enabled:
            print(f"Skipping {name} (disabled)")
            continue
        if name in AGENTS_WITH_AI and not settings.enable_ai:
            print(f"Skipping {name} (requires AI, but ENABLE_AI is false)")
            continue
        try:
            all_results[name] = run_agent(name, settings, provider, model)
        except Exception as e:
            print(f"Error running {name}: {e}")
            all_results[name] = {"error": str(e)}
    return all_results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Run GitHub Assistance Agents")
    parser.add_argument("agent", choices=[*AGENT_REGISTRY.keys(), "all"], help="Agent to run")
    parser.add_argument("--pr", help="PR reference (owner/repo#number)")
    parser.add_argument("--ai-provider", help="Override AI provider")
    parser.add_argument("--ai-model", help="Override AI model")
    args = parser.parse_args()

    settings = Settings.from_env()

    if args.agent == "all":
        results = run_all(settings, args.ai_provider, args.ai_model)
    else:
        results = run_agent(args.agent, settings, args.ai_provider, args.ai_model, args.pr)

    deps = _create_base_deps(settings)
    send_execution_report(deps["telegram"], args.agent, results)

    print(f"\n{'='*60}\nExecution complete\n{'='*60}")


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
