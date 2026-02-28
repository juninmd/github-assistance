"""
Application settings and configuration.
"""
import os
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
SUPPORTED_AI_PROVIDERS = {"gemini", "ollama", "openai"}

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "ollama": "llama3",
    "openai": "gpt-4o",
}


def _parse_bool(value: str | None, default: bool) -> bool:
    """Parse boolean-like environment values with safe defaults."""
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def _parse_positive_int(value: str | None, default: int, env_name: str) -> int:
    """Parse a positive integer env var value or raise a clear validation error."""
    if value is None:
        return default

    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{env_name} must be a positive integer")
    return parsed


@dataclass
class Settings:
    """
    Global application settings.
    """
    # Required fields (no defaults)
    github_token: str

    # Optional fields (with defaults)
    jules_api_key: str | None = None
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
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
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
        provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
        if provider not in SUPPORTED_AI_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_AI_PROVIDERS))
            raise ValueError(f"AI_PROVIDER must be one of: {supported}")

        # Determine default model based on provider if not explicitly set
        default_model = DEFAULT_MODELS.get(provider, "gemini-2.5-flash")
        ai_model = os.getenv("AI_MODEL", default_model).strip() or default_model

        return cls(
            github_token=github_token,
            github_owner=os.getenv("GITHUB_OWNER", "juninmd"),
            jules_api_key=jules_api_key,
            product_manager_enabled=_parse_bool(os.getenv("PM_AGENT_ENABLED"), True),
            interface_developer_enabled=_parse_bool(os.getenv("UI_AGENT_ENABLED"), True),
            senior_developer_enabled=_parse_bool(os.getenv("DEV_AGENT_ENABLED"), True),
            pr_assistant_enabled=_parse_bool(os.getenv("PR_ASSISTANT_ENABLED"), True),
            repository_allowlist_path=os.getenv("REPOSITORY_ALLOWLIST_PATH", "config/repositories.json"),
            agent_run_interval_hours=_parse_positive_int(
                os.getenv("AGENT_RUN_INTERVAL_HOURS"),
                24,
                "AGENT_RUN_INTERVAL_HOURS"
            ),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            ai_provider=provider,
            ai_model=ai_model,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
