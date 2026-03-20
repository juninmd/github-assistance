"""
Central runner for all AI agents.
Usage: uv run run-agent <agent-name> [--pr owner/repo#number] [--ai-provider gemini] [--ai-model gemini-2.5-flash]
"""
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.ci_health.agent import CIHealthAgent
from src.agents.code_reviewer.agent import CodeReviewerAgent
from src.agents.conflict_resolver.agent import ConflictResolverAgent
from src.agents.interface_developer.agent import InterfaceDeveloperAgent
from src.agents.jules_tracker.agent import JulesTrackerAgent
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.agents.pr_sla.agent import PRSLAAgent
from src.agents.product_manager.agent import ProductManagerAgent
from src.agents.project_creator.agent import ProjectCreatorAgent
from src.agents.secret_remover.agent import SecretRemoverAgent
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
    "secret-remover": SecretRemoverAgent,
    "project-creator": ProjectCreatorAgent,
    "conflict-resolver": ConflictResolverAgent,
    "code-reviewer": CodeReviewerAgent,
}

AGENTS_WITH_AI = {
    "product-manager", "interface-developer", "senior-developer",
    "pr-assistant", "jules-tracker", "secret-remover",
    "project-creator", "conflict-resolver", "code-reviewer"
}


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

    # Override telegram dependency to include the agent-specific prefix
    kwargs["telegram"] = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        prefix=f"[{agent_name.replace('-', ' ').upper()}]"
    )
    kwargs["target_owner"] = settings.github_owner

    if agent_name in AGENTS_WITH_AI:
        if not settings.enable_ai:
            raise PermissionError(f"Agent '{agent_name}' requires AI but ENABLE_AI is false.")
        kwargs.update(_build_ai_config(settings, provider, model))

    # Agents that support direct PR reference
    if agent_name in ["pr-assistant", "code-reviewer", "conflict-resolver"] and pr_ref:
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

    if agent_name == "all":
        # Summary for multiple agents
        for name, res in results.items():
            status = "❌" if "error" in res else "✅"
            lines.append(f"{status} `{esc(name)}`")
            if "error" in res:
                err_msg = str(res['error']).split("\n")[0][:100]
                lines.append(f"  └ ⚠️ Error: `{esc(err_msg)}`")
    else:
        # Detailed report for a single agent
        if "error" in results:
            lines.append("❌ Status: *Falha Crítica*")
            err_msg = str(results['error']).split("\n")[0][:200]
            lines.append(f"⚠️ Erro: `{esc(err_msg)}`")
        else:
            lines.append("✅ Status: *Sucesso*")
            processed = results.get("processed", results.get("merged", results.get("resolved", [])))
            failed = results.get("failed", [])

            # Show stats only if they are not 0 to keep it concise
            if isinstance(processed, (list, dict)) and len(processed) > 0:
                lines.append(f"📈 Processados: *{len(processed)}*")
            elif isinstance(processed, (int, float)) and processed > 0:
                lines.append(f"📈 Processados: *{processed}*")

            if isinstance(failed, (list, dict)) and len(failed) > 0:
                lines.append(f"❌ Falhas: *{len(failed)}*")
            elif isinstance(failed, (int, float)) and failed > 0:
                lines.append(f"❌ Falhas: *{failed}*")

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
        "pr-sla": settings.enable_pr_sla,
        "jules-tracker": settings.enable_jules_tracker,
        "secret-remover": settings.enable_secret_remover,
        "project-creator": settings.enable_project_creator,
        "conflict-resolver": True, # Always enabled if run via 'all'
        "code-reviewer": True,
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
    results = {}

    try:
        if args.agent == "all":
            results = run_all(settings, args.ai_provider, args.ai_model)
        else:
            results = run_agent(args.agent, settings, args.ai_provider, args.ai_model, args.pr)
    except Exception as e:
        print(f"Execution failed: {e}")
        traceback.print_exc()
        results = {"error": str(e)}

    # Always notify status on Telegram
    try:
        deps = _create_base_deps(settings)
        send_execution_report(deps["telegram"], args.agent, results)
    except Exception as notify_err:
        print(f"Failed to send Telegram report: {notify_err}", file=sys.stderr)

    if "error" in results and args.agent != "all":
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
