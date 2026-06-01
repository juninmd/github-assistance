"""
Homologation script for Conflict Resolver Agent.
Runs the agent with real calls to verify the expanded search logic.
"""

import os
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from src.agents.registry import create_agent
from src.config.settings import Settings


def main():
    print("🚀 Starting Conflict Resolver Homologation...")

    try:
        settings = Settings.from_env()
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        return

    print(f"Target Owner: {settings.github_owner}")
    print(f"AI Provider: {settings.ai_provider}")
    print(f"AI Model: {settings.ai_model}")

    # Create the agent
    agent = create_agent("conflict-resolver", settings)

    print("\n🔍 Running Agent...")
    results = agent.run()

    print("\n✅ Execution Finished")
    print(f"Timestamp: {results.get('timestamp')}")
    print(f"Resolved: {len(results.get('resolved', []))}")
    print(f"Closed: {len(results.get('closed', []))}")

    for item in results.get("resolved", []):
        print(f"  - [RESOLVED] PR #{item['pr']} in {item['repo']}: {item['msg']}")

    for item in results.get("closed", []):
        print(f"  - [CLOSED] PR #{item['pr']} in {item['repo']}: {item['error']}")


if __name__ == "__main__":
    main()
