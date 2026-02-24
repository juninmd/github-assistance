"""
Agent runner module - Entry point for executing individual agents.
"""
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import Settings, RepositoryAllowlist
from src.jules import JulesClient
from src.github_client import GithubClient
from src.agents import (
    ProductManagerAgent,
    InterfaceDeveloperAgent,
    SeniorDeveloperAgent,
    PRAssistantAgent,
    SecurityScannerAgent,
    CIHealthAgent,
    ReleaseWatcherAgent,
    DependencyRiskAgent,
    PRSLAAgent,
    IssueEscalationAgent
)


def ensure_logs_dir():
    """Ensure logs directory exists."""
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


def save_results(agent_name: str, results: dict):
    """
    Save agent execution results to a JSON file.

    Args:
        agent_name: Name of the agent
        results: Execution results dictionary
    """
    logs_dir = ensure_logs_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = logs_dir / f"{agent_name}-{timestamp}.json"

    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {filename}")


def run_product_manager():
    """Run the Product Manager agent."""
    print("=" * 60)
    print("Running Product Manager Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = ProductManagerAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist
    )

    results = agent.run()
    save_results("product-manager", results)
    return results


def run_interface_developer():
    """Run the Interface Developer agent."""
    print("=" * 60)
    print("Running Interface Developer Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = InterfaceDeveloperAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist
    )

    results = agent.run()
    save_results("interface-developer", results)
    return results


def run_senior_developer():
    """Run the Senior Developer agent."""
    print("=" * 60)
    print("Running Senior Developer Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = SeniorDeveloperAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist
    )

    results = agent.run()
    save_results("senior-developer", results)
    return results


def run_pr_assistant(pr_ref: Optional[str] = None, ai_provider: Optional[str] = None, ai_model: Optional[str] = None):
    """Run the PR Assistant agent."""
    print("=" * 60)
    print(f"Running PR Assistant Agent{' for ' + pr_ref if pr_ref else ''}")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    # Determine AI provider and model (CLI args override settings)
    provider = ai_provider or settings.ai_provider
    model = ai_model or settings.ai_model

    ai_config = {}
    if provider == "ollama":
        ai_config["base_url"] = settings.ollama_base_url
    elif provider == "gemini":
        ai_config["api_key"] = settings.gemini_api_key
    elif provider == "openai":
        ai_config["api_key"] = settings.openai_api_key

    agent = PRAssistantAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner,
        ai_provider=provider,
        ai_model=model,
        ai_config=ai_config
    )

    results = agent.run(specific_pr=pr_ref)
    save_results("pr-assistant", results)
    return results


def run_security_scanner():
    """Run the Security Scanner agent."""
    print("=" * 60)
    print("Running Security Scanner Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = SecurityScannerAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("security-scanner", results)
    return results


def run_ci_health():
    """Run the CI Health agent."""
    print("=" * 60)
    print("Running CI Health Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = CIHealthAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("ci-health", results)
    return results


def run_release_watcher():
    """Run the Release Watcher agent."""
    print("=" * 60)
    print("Running Release Watcher Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = ReleaseWatcherAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("release-watcher", results)
    return results


def run_dependency_risk():
    """Run the Dependency Risk agent."""
    print("=" * 60)
    print("Running Dependency Risk Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = DependencyRiskAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("dependency-risk", results)
    return results


def run_pr_sla():
    """Run the PR SLA agent."""
    print("=" * 60)
    print("Running PR SLA Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = PRSLAAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("pr-sla", results)
    return results


def run_issue_escalation():
    """Run the Issue Escalation agent."""
    print("=" * 60)
    print("Running Issue Escalation Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()

    agent = IssueEscalationAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("issue-escalation", results)
    return results


def main():
    """
    Main entry point for running agents.

    Usage:
        uv run run-agent <agent-name> [--provider <provider>] [--model <model>] [pr_ref]
    """
    parser = argparse.ArgumentParser(description="Run specific AI agent.")
    parser.add_argument("agent_name", choices=[
        "product-manager",
        "interface-developer",
        "senior-developer",
        "pr-assistant",
        "security-scanner",
        "ci-health",
        "release-watcher",
        "dependency-risk",
        "pr-sla",
        "issue-escalation",
        "all"
    ], help="The name of the agent to run.")

    parser.add_argument("pr_ref", nargs="?", help="Optional PR reference for pr-assistant (e.g., owner/repo#123 or 123).")

    parser.add_argument("--provider", choices=["gemini", "ollama", "openai"], help="AI provider to use (overrides env var).")
    parser.add_argument("--model", help="AI model to use (overrides env var).")

    args = parser.parse_args()

    agents = {
        "product-manager": run_product_manager,
        "interface-developer": run_interface_developer,
        "senior-developer": run_senior_developer,
        "pr-assistant": run_pr_assistant,
        "security-scanner": run_security_scanner,
        "ci-health": run_ci_health,
        "release-watcher": run_release_watcher,
        "dependency-risk": run_dependency_risk,
        "pr-sla": run_pr_sla,
        "issue-escalation": run_issue_escalation,
    }

    if args.agent_name == "all":
        print("Running all agents sequentially...")
        all_results = {}
        for name, runner in agents.items():
            try:
                # PR assistant needs special handling if run in 'all' mode without PR ref
                # But typically 'all' mode is for scheduled runs scanning all PRs
                if name == "pr-assistant":
                    results = runner(ai_provider=args.provider, ai_model=args.model)
                else:
                    results = runner()
                all_results[name] = results
            except Exception as e:
                print(f"Error running {name}: {e}")
                all_results[name] = {"error": str(e)}

        save_results("all-agents", all_results)
        return

    try:
        runner = agents[args.agent_name]
        if args.agent_name == "pr-assistant":
            # Pass pr_ref only if it's provided, otherwise it defaults to None in the function
            runner(pr_ref=args.pr_ref, ai_provider=args.provider, ai_model=args.model)
        else:
            # Other agents currently don't accept provider/model overrides in their run function
            # But we could extend them if needed. For now, we just run them.
            runner()
    except Exception as e:
        print(f"Error running agent: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()  # pragma: no cover
