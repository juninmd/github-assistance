"""
Agent runner module - Entry point for executing individual agents.
"""
import sys
import json
import os
from datetime import datetime
from pathlib import Path

from src.config import Settings, RepositoryAllowlist
from src.jules import JulesClient
from src.github_client import GithubClient
from src.ai_client import GeminiClient
from src.agents import (
    ProductManagerAgent,
    InterfaceDeveloperAgent,
    SeniorDeveloperAgent,
    PRAssistantAgent
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


def run_pr_assistant():
    """Run the PR Assistant agent."""
    print("=" * 60)
    print("Running PR Assistant Agent")
    print("=" * 60)

    settings = Settings.from_env()
    allowlist = RepositoryAllowlist(settings.repository_allowlist_path)
    jules_client = JulesClient(settings.jules_api_key)
    github_client = GithubClient()
    ai_client = GeminiClient()

    agent = PRAssistantAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        ai_client=ai_client,
        target_owner=settings.github_owner
    )

    results = agent.run()
    save_results("pr-assistant", results)
    return results


def main():
    """
    Main entry point for running agents.

    Usage:
        uv run run-agent <agent-name>

    Agent names:
        - product-manager
        - interface-developer
        - senior-developer
        - pr-assistant
        - all  (runs all agents sequentially)
    """
    if len(sys.argv) < 2:
        print("Usage: uv run run-agent <agent-name>")
        print("\nAvailable agents:")
        print("  - product-manager")
        print("  - interface-developer")
        print("  - senior-developer")
        print("  - pr-assistant")
        print("  - all")
        sys.exit(1)

    agent_name = sys.argv[1].lower()

    agents = {
        "product-manager": run_product_manager,
        "interface-developer": run_interface_developer,
        "senior-developer": run_senior_developer,
        "pr-assistant": run_pr_assistant,
    }

    if agent_name == "all":
        print("Running all agents sequentially...")
        all_results = {}
        for name, runner in agents.items():
            try:
                results = runner()
                all_results[name] = results
            except Exception as e:
                print(f"Error running {name}: {e}")
                all_results[name] = {"error": str(e)}

        save_results("all-agents", all_results)
        return

    if agent_name not in agents:
        print(f"Unknown agent: {agent_name}")
        print(f"Available agents: {', '.join(agents.keys())}, all")
        sys.exit(1)

    try:
        agents[agent_name]()
    except Exception as e:
        print(f"Error running agent: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
