from __future__ import annotations

import argparse
import sys

from src.agents.pr_assistant import PRAssistantAgent
from src.config import RepositoryAllowlist, Settings
from src.github_client import GithubClient
from src.jules import JulesClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PR Assistant Agent.")
    parser.add_argument("pr_ref", nargs="?", help="Optional PR reference (e.g., owner/repo#123 or 123).")
    parser.add_argument("--provider", choices=["gemini", "ollama", "openai"], help="AI provider to use (overrides env var).")
    parser.add_argument("--model", help="AI model to use (overrides env var).")

    args = parser.parse_args()

    try:
        settings = Settings.from_env()

        github_client = GithubClient()
        jules_client = JulesClient(settings.jules_api_key)

        allowlist = RepositoryAllowlist(settings.repository_allowlist_path)

        provider = args.provider or settings.ai_provider or ""
        model = args.model or settings.ai_model or ""

        ai_config: dict[str, str] = {}
        match provider:
            case "ollama":
                ai_config["base_url"] = settings.ollama_base_url or ""
            case "gemini":
                ai_config["api_key"] = settings.gemini_api_key or ""
            case "openai":
                ai_config["api_key"] = settings.openai_api_key or ""

        if args.provider and not args.model:
            from src.config.settings import DEFAULT_MODELS
            model = DEFAULT_MODELS.get(provider, model)

        agent = PRAssistantAgent(
            jules_client=jules_client,
            github_client=github_client,
            allowlist=allowlist,
            target_owner=settings.github_owner,
            ai_provider=provider,
            ai_model=model,
            ai_config=ai_config,
            pr_ref=args.pr_ref
        )
        agent.run()
    except Exception as e:
        print(f"Error running agent: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
