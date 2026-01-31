import os
import sys
from src.agent import Agent
from src.github_client import GithubClient
from src.ai_client import GeminiClient

def main():
    """
    Main entry point for the PR Assistant Agent.
    """
    try:
        # Initialize clients with environment variables
        github_client = GithubClient()
        # Default to GeminiClient as per instructions for production use
        ai_client = GeminiClient()

        agent = Agent(github_client, ai_client)
        agent.run()
    except Exception as e:
        print(f"Error running agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
