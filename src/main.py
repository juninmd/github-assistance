import argparse
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
    parser = argparse.ArgumentParser(description="Run PR Assistant Agent.")
    parser.add_argument("pr_ref", nargs="?", help="Optional PR reference (e.g., owner/repo#123 or 123).")
    parser.add_argument("--provider", choices=["gemini", "ollama", "openai"], help="AI provider to use (overrides env var).")
    parser.add_argument("--model", help="AI model to use (overrides env var).")

    args = parser.parse_args()

    try:
        # Load settings
        settings = Settings.from_env()

        # Initialize clients
        github_client = GithubClient()
        jules_client = JulesClient(settings.jules_api_key)

        # Note: allowlist is passed to BaseAgent but PR Assistant doesn't use it
        # PR Assistant works on ALL repositories owned by target_owner
        allowlist = RepositoryAllowlist(settings.repository_allowlist_path)

        # Determine AI provider and model (CLI args override settings)
        provider = args.provider or settings.ai_provider
        model = args.model or settings.ai_model

        # Create and run PR Assistant (works on ALL repositories)
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
        agent.run(specific_pr=args.pr_ref)
    except Exception as e:
        print(f"Error running agent: {e}")  # pragma: no cover
        sys.exit(1)  # pragma: no cover

if __name__ == "__main__":
    main()  # pragma: no cover
