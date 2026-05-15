"""
Central runner for all AI agents.
Usage: uv run run-agent <agent-name> [--pr owner/repo#number] [--ai-provider gemini] [--ai-model gemini-2.5-flash]
"""
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from src.agents.metrics import AgentMetrics
from src.utils.logger import get_logger, new_correlation_id

_log = get_logger("run-agent")

from src.agents.base_agent import BaseAgent
from src.agents.branch_cleaner.agent import BranchCleanerAgent
from src.agents.ci_health.agent import CIHealthAgent
from src.agents.code_reviewer.agent import CodeReviewerAgent
from src.agents.intelligence_standardizer.agent import IntelligenceStandardizerAgent
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
    "branch-cleaner": BranchCleanerAgent,
    "intelligence-standardizer": IntelligenceStandardizerAgent,
}

AGENTS_WITH_AI = {
    "product-manager", "interface-developer", "senior-developer", 
    "pr-assistant", "jules-tracker", "secret-remover", 
    "project-creator", "conflict-resolver", "code-reviewer",
    "intelligence-standardizer"
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


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _build_agent_header(telegram, agent_name, results, duration_str):
    """Build the common header for all execution reports."""
    esc = telegram.escape_html
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = [
        "🤖 <b>GITHUB ASSISTANCE REPORT</b>",
        f"📅 <code>{esc(now)}</code>",
        f"👤 <b>Agente:</b> <code>{esc(agent_name.replace('-', ' ').upper())}</code>",
        f"⏱️ <b>Duração:</b> <code>{esc(duration_str)}</code>",
        "──────────────────────",
    ]
    success_rate = results.get("_metrics", {}).get("success_rate")
    if success_rate is not None:
        lines.append(f"📊 <b>Taxa de sucesso:</b> <code>{success_rate:.0f}%</code>")
    return lines


def _build_all_agents_report(telegram, results):
    """Build report lines when running all agents."""
    esc = telegram.escape_html
    lines = []
    success_count = 0
    fail_count = 0
    for name, res in results.items():
        if "error" in res:
            fail_count += 1
            err_msg = str(res['error']).split("\n")[0][:100]
            lines.append(f"❌ *{esc(name)}*")
            lines.append(f"  └ ⚠️ `{esc(err_msg)}`")
        else:
            success_count += 1
            lines.append(f"✅ *{esc(name)}*")
    lines.append("──────────────────────")
    lines.append(f"📊 <b>Resumo:</b> ✅ <code>{success_count}</code> | ❌ <code>{fail_count}</code>")
    return lines


def _build_single_agent_report(telegram, agent_name, results):
    """Build detailed report lines for a single agent."""
    esc = telegram.escape_html
    lines = []
    if "error" in results:
        lines.append("💥 <b>STATUS: FALHA CRÍTICA</b>")
        err_msg = str(results['error']).split("\n")[0][:250]
        lines.append(f"⚠️ <b>Erro:</b> <code>{esc(err_msg)}</code>")
        return lines

    lines.append("🚀 <b>STATUS: OPERAÇÃO CONCLUÍDA</b>")

    # Agent-specific details
    if agent_name == "senior-developer":
        sec = len(results.get("security_tasks", []))
        cicd = len(results.get("cicd_tasks", []))
        feat = len(results.get("feature_tasks", []))
        debt = len(results.get("tech_debt_tasks", []))
        if any([sec, cicd, feat, debt]):
            task_lines = []
            if sec: task_lines.append(f"  🛡️ Segurança: <b>{sec}</b>")
            if cicd: task_lines.append(f"  ⚙️ CI/CD: <b>{cicd}</b>")
            if feat: task_lines.append(f"  ✨ Features: <b>{feat}</b>")
            if debt: task_lines.append(f"  🧹 Débito Técnico: <b>{debt}</b>")
            lines.append("\n🛠️ <b>Tarefas Criadas:</b>")
            lines.extend(task_lines)

    # General stats
    processed = results.get("processed", results.get("merged", results.get("resolved", [])))
    failed = results.get("failed", [])
    if isinstance(processed, (list, dict)) and len(processed) > 0:
        lines.append(f"\n📈 <b>Itens Processados:</b> <code>{len(processed)}</code>")
    elif isinstance(processed, (int, float)) and processed > 0:
        lines.append(f"\n📈 <b>Itens Processados:</b> <code>{processed}</code>")

    if isinstance(failed, (list, dict)) and len(failed) > 0:
        lines.append(f"❌ <b>Falhas:</b> <code>{len(failed)}</code>")
        for f in failed[:3]:
            repo = f.get("repository", "unknown")
            err = str(f.get("error", "unknown")).split("\n")[0][:50]
            lines.append(f"  └ <code>{esc(repo)}</code>: <i>{esc(err)}</i>")
    return lines


def send_execution_report(telegram: TelegramNotifier, agent_name: str, results: dict[str, Any]) -> None:
    if agent_name == "pr-assistant":
        return

    metrics = results.get("_metrics", {})
    duration_s = metrics.get("duration_seconds")
    duration_str = _format_duration(duration_s) if duration_s is not None else "—"

    lines = _build_agent_header(telegram, agent_name, results, duration_str)
    if agent_name == "all":
        lines.extend(_build_all_agents_report(telegram, results))
    else:
        lines.extend(_build_single_agent_report(telegram, agent_name, results))

    telegram.send_message("\n".join(lines), parse_mode="HTML")


# --- CLI entry point ----------------------------------------------------------

def run_agent(agent_name: str, settings: Settings, provider: str | None = None, model: str | None = None, pr_ref: str | None = None) -> dict[str, Any]:
    """Run a single agent, track metrics, and save results."""
    cid = new_correlation_id()
    _log.info(f"{'='*60}")
    _log.info(f"Starting agent: {agent_name}", correlation_id=cid)
    _log.info(f"{'='*60}")

    metrics = AgentMetrics(agent_name)
    t0 = time.monotonic()
    results: dict[str, Any] = {}
    try:
        agent = _create_agent(agent_name, settings, provider, model, pr_ref)
        results = agent.run()
        duration = time.monotonic() - t0
        metrics.increment_processed(len(results) if isinstance(results, dict) else 1)
        _log.info(f"Agent {agent_name} completed in {duration:.1f}s")
    except Exception as exc:
        duration = time.monotonic() - t0
        metrics.add_error(str(exc))
        metrics.increment_failed()
        _log.error(f"Agent {agent_name} failed after {duration:.1f}s: {exc}")
        results = {"error": str(exc)}
        raise
    finally:
        results.setdefault("_metrics", metrics.finalize())
        save_results(agent_name, results)
    return results


def _get_enabled_agents(settings: Settings) -> list[str]:
    """Return list of enabled agent names based on settings."""
    enabled_map: dict[str, bool] = {
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
    enabled = []
    for name, is_enabled in enabled_map.items():
        if not is_enabled:
            print(f"Skipping {name} (disabled)")
            continue
        if name in AGENTS_WITH_AI and not settings.enable_ai:
            print(f"Skipping {name} (requires AI, but ENABLE_AI is false)")
            continue
        enabled.append(name)
    return enabled


def run_all(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Run all enabled agents in parallel using a thread pool."""
    all_results: dict[str, Any] = {}
    enabled_agents = _get_enabled_agents(settings)

    if not enabled_agents:
        return all_results

    with ThreadPoolExecutor(max_workers=min(8, len(enabled_agents))) as executor:
        futures = {
            executor.submit(run_agent, name, settings, provider, model): name
            for name in enabled_agents
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                all_results[name] = future.result()
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

    from src.utils.health import run_health_checks
    health = run_health_checks(settings, args.agent)
    _log.info("Health check results:\n" + health.summary())
    if not health.ok:
        _log.error("Pre-flight checks failed — aborting agent run")
        sys.exit(1)

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
