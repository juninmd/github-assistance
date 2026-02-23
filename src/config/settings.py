"""
Application settings and configuration.
"""
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class Settings:
    """
    Global application settings.
    """
    # Required fields (no defaults)
    github_token: str

    # Optional fields (with defaults)
    jules_api_key: Optional[str] = None
    github_owner: str = "juninmd"

    # Agent Configuration
    product_manager_enabled: bool = True
    interface_developer_enabled: bool = True
    senior_developer_enabled: bool = True
    pr_assistant_enabled: bool = True

    # Repository Configuration
    repository_allowlist_path: str = "config/repositories.json"

    # Scheduling
    agent_run_interval_hours: int = 24

    # AI Configuration
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ai_provider: str = "gemini"
    ai_model: str = "gemini-2.5-flash"
    ollama_base_url: str = "http://localhost:11434"

    @classmethod
    def from_env(cls) -> 'Settings':
        """
        Create settings from environment variables.

        Returns:
            Settings instance populated from environment
        """
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")

        jules_api_key = os.getenv("JULES_API_KEY")

        return cls(
            github_token=github_token,
            github_owner=os.getenv("GITHUB_OWNER", "juninmd"),
            jules_api_key=jules_api_key,
            product_manager_enabled=os.getenv("PM_AGENT_ENABLED", "true").lower() == "true",
            interface_developer_enabled=os.getenv("UI_AGENT_ENABLED", "true").lower() == "true",
            senior_developer_enabled=os.getenv("DEV_AGENT_ENABLED", "true").lower() == "true",
            pr_assistant_enabled=os.getenv("PR_ASSISTANT_ENABLED", "true").lower() == "true",
            repository_allowlist_path=os.getenv("REPOSITORY_ALLOWLIST_PATH", "config/repositories.json"),
            agent_run_interval_hours=int(os.getenv("AGENT_RUN_INTERVAL_HOURS", "24")),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            ai_provider=os.getenv("AI_PROVIDER", "gemini"),
            ai_model=os.getenv("AI_MODEL", "gemini-2.5-flash"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
