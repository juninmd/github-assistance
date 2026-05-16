"""
Central runner for all AI agents.
Usage: uv run run-agent <agent-name> [--pr owner/repo#number] [--ai-provider gemini] [--ai-model gemini-2.5-flash]
"""
import argparse
import sys
import time
import traceback
from typing import Any

from src.agents.metrics import AgentMetrics
from src.agents.registry import AGENT_REGISTRY, AGENTS_WITH_AI
from src.agents.reporting import save_results, send_execution_report
from src.config.repository_allowlist import RepositoryAllowlist
from src.config.settings import DEFAULT_MODELS, Settings
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier
from src.utils.health import run_health_checks
from src.utils.logger import get_logger, new_correlation_id

_log = get_logger("run-agent")


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

    if provider and not model:
        resolved_model = DEFAULT_MODELS.get(resolved_provider, resolved_model)

    match resolved_provider:
        case "gemini":
            config["api_key"] = settings.gemini_api_key
        case "openai":
            config["api_key"] = settings.openai_api_key
        case "ollama":
            config["base_url"] = settings.ollama_base_url

    return {"ai_provider": resolved_provider, "ai_model": resolved_model, "ai_config": config}


def _create_agent(
    agent_name: str, settings: Settings,
    provider: str | None = None, model: str | None = None,
    pr_ref: str | None = None,
) -> Any:
    """Instantiate any agent by name with all dependencies."""
    agent_cls = AGENT_REGISTRY[agent_name]
    deps = _create_base_deps(settings)
    kwargs: dict[str, Any] = {**deps}

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

    if agent_name in ["pr-assistant", "code-reviewer", "conflict-resolver"] and pr_ref:
        kwargs["pr_ref"] = pr_ref

    return agent_cls(**kwargs)


def run_agent(
    agent_name: str, settings: Settings,
    provider: str | None = None, model: str | None = None,
    pr_ref: str | None = None,
) -> dict[str, Any]:
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


def run_all(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Run all enabled agents in parallel batches respecting dependencies."""
    from src.agents.batch_runner import run_all as _run_all
    return _run_all(settings, provider, model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GitHub Assistance Agents")
    parser.add_argument("agent", choices=[*AGENT_REGISTRY.keys(), "all"], help="Agent to run")
    parser.add_argument("--pr", help="PR reference (owner/repo#number)")
    parser.add_argument("--ai-provider", help="Override AI provider")
    parser.add_argument("--ai-model", help="Override AI model")
    args = parser.parse_args()

    settings = Settings.from_env()
    results = {}

    health = run_health_checks(settings, args.agent)
    _log.info("Health check results:\n" + health.summary())
    if not health.ok:
        _log.error("Pre-flight checks failed \u2014 aborting agent run")
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

    try:
        deps = _create_base_deps(settings)
        send_execution_report(deps["telegram"], args.agent, results)
    except Exception as notify_err:
        print(f"Failed to send Telegram report: {notify_err}", file=sys.stderr)

    if "error" in results and args.agent != "all":
        sys.exit(1)


if __name__ == "__main__":
    main()
