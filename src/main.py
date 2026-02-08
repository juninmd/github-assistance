import os
import sys
from src.agents.pr_assistant import PRAssistantAgent
from src.github_client import GithubClient
from src.jules import JulesClient
from src.config import RepositoryAllowlist, Settings

def main():
    """
    Main entry point for the PR Assistant Agent.
    Legacy compatibility - use run_agent.py for new workflow.
    """
    try:
        # Load settings
        settings = Settings.from_env()

        # Initialize clients
        github_client = GithubClient()
        jules_client = JulesClient(settings.jules_api_key)

        # Note: allowlist is passed to BaseAgent but PR Assistant doesn't use it
        # PR Assistant works on ALL repositories owned by target_owner
        allowlist = RepositoryAllowlist(settings.repository_allowlist_path)

        # Create and run PR Assistant (works on ALL repositories)
        agent = PRAssistantAgent(
            jules_client=jules_client,
            github_client=github_client,
            allowlist=allowlist,
            target_owner=settings.github_owner
        )
        agent.run()
    except Exception as e:
        print(f"Error running agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
