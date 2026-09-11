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
from src.agents.registry import AGENT_REGISTRY, create_agent, create_base_deps
from src.agents.reporting import save_results, send_execution_report
from src.config.settings import Settings
from src.results import RunResult
from src.utils.health import run_health_checks
from src.utils.logger import get_logger, new_correlation_id

_log = get_logger("run-agent")


def is_failed_result(result: dict[str, Any]) -> bool:
    """Return True when an agent result represents a failed run."""
    if "error" in result or result.get("status") == "failed":
        return True
    run_result = result.get("_run_result")
    # Blocked PRs (CI pending, observe mode) are routine waits, not a failed run.
    return bool(run_result and run_result.get("status") == "failed")


def run_agent(
    agent_name: str,
    settings: Settings,
    provider: str | None = None,
    model: str | None = None,
    pr_ref: str | None = None,
) -> dict[str, Any]:
    """Run a single agent, track metrics, and save results."""
    cid = new_correlation_id()
    _log.info(f"{'=' * 60}")
    _log.info(f"Starting agent: {agent_name}", correlation_id=cid)
    _log.info(f"{'=' * 60}")

    metrics = AgentMetrics(agent_name)
    t0 = time.monotonic()
    results: dict[str, Any] = {}
    task_id = new_correlation_id() or cid
    try:
        agent = create_agent(agent_name, settings, provider, model, pr_ref)
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
    finally:
        final_metrics = metrics.finalize()
        results.setdefault("_metrics", final_metrics)
        run_result = RunResult.from_agent_dict(agent_name, results, task_id=task_id)
        run_result.duration_seconds = final_metrics.get("duration_seconds", 0.0)
        run_result.task_id = task_id
        run_result.pr_ref = pr_ref
        results["_run_result"] = run_result.to_dict()
        save_results(agent_name, results)
    return results


def run_all(
    settings: Settings, provider: str | None = None, model: str | None = None
) -> dict[str, Any]:
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
        deps = create_base_deps(settings)
        send_execution_report(deps["telegram"], args.agent, results)
    except Exception as notify_err:
        print(f"Failed to send Telegram report: {notify_err}", file=sys.stderr)

    if args.agent == "all":
        if _any_batch_failure(results):
            sys.exit(1)
    elif is_failed_result(results):
        sys.exit(1)


def _any_batch_failure(results: dict[str, Any]) -> bool:
    """Return True when any agent in a batch run failed."""
    if "error" in results or results.get("status") == "failed":
        return True
    return any(is_failed_result(res) for res in results.values() if isinstance(res, dict))


if __name__ == "__main__":
    main()
