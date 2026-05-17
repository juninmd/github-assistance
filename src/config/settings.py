"""
Application settings and configuration.
"""
import os
from dataclasses import dataclass
from typing import Self

from dotenv import load_dotenv

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
SUPPORTED_AI_PROVIDERS = {"gemini", "ollama", "openai"}

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "ollama": "qwen3:1.7b",
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

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{env_name} must be a positive integer") from exc

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

    # Agent Enablement
    enable_product_manager: bool = True
    enable_interface_developer: bool = True
    enable_senior_developer: bool = True
    enable_pr_assistant: bool = True
    enable_security_scanner: bool = True
    enable_ci_health: bool = True
    enable_release_watcher: bool = True
    enable_dependency_risk: bool = True
    enable_pr_sla: bool = True
    enable_issue_escalation: bool = True
    enable_jules_tracker: bool = True
    enable_secret_remover: bool = True
    enable_project_creator: bool = True
    enable_branch_cleaner: bool = True
    enable_intelligence_standardizer: bool = True
    enable_ai: bool = False

    # Repository Configuration
    repository_allowlist_path: str = "config/repositories.json"

    # Scheduling
    agent_run_interval_hours: int = 24

    # AI Configuration
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    ai_provider: str = "ollama"
    ai_model: str = "qwen3:1.7b"
    ollama_base_url: str = "http://localhost:11434"

    # Telegram
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @classmethod
    def from_env(cls) -> Self:
        """
        Create settings from environment variables.

        Returns:
            Settings instance populated from environment
        """
        load_dotenv()
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")

        jules_api_key = os.getenv("JULES_API_KEY")
        enable_ai = _parse_bool(os.getenv("ENABLE_AI"), False)
        raw_provider = os.getenv("AI_PROVIDER", "ollama").strip().lower()
        provider = raw_provider or "ollama"

        if provider not in SUPPORTED_AI_PROVIDERS:
            if enable_ai:
                supported = ", ".join(sorted(SUPPORTED_AI_PROVIDERS))
                raise ValueError(f"AI_PROVIDER must be one of: {supported}")
            provider = "ollama"

        # Determine default model based on provider if not explicitly set
        default_model = DEFAULT_MODELS.get(provider, "gemini-2.5-flash")
        ai_model = os.getenv("AI_MODEL", default_model).strip() or default_model

        return cls(
            github_token=github_token,
            github_owner=os.getenv("GITHUB_OWNER", "juninmd"),
            jules_api_key=jules_api_key,
            enable_product_manager=_parse_bool(os.getenv("PM_AGENT_ENABLED"), True),
            enable_interface_developer=_parse_bool(os.getenv("UI_AGENT_ENABLED"), True),
            enable_senior_developer=_parse_bool(os.getenv("DEV_AGENT_ENABLED"), True),
            enable_pr_assistant=_parse_bool(os.getenv("PR_ASSISTANT_ENABLED"), True),
            enable_security_scanner=_parse_bool(os.getenv("SECURITY_SCANNER_ENABLED"), True),
            enable_ci_health=_parse_bool(os.getenv("CI_HEALTH_ENABLED"), True),
            enable_release_watcher=_parse_bool(os.getenv("RELEASE_WATCHER_ENABLED"), True),
            enable_dependency_risk=_parse_bool(os.getenv("DEPENDENCY_RISK_ENABLED"), True),
            enable_pr_sla=_parse_bool(os.getenv("PR_SLA_ENABLED"), True),
            enable_issue_escalation=_parse_bool(os.getenv("ISSUE_ESCALATION_ENABLED"), True),
            enable_jules_tracker=_parse_bool(os.getenv("JULES_TRACKER_ENABLED"), True),
            enable_secret_remover=_parse_bool(os.getenv("SECRET_REMOVER_ENABLED"), True),
            enable_project_creator=_parse_bool(os.getenv("PROJECT_CREATOR_ENABLED"), True),
            enable_branch_cleaner=_parse_bool(os.getenv("BRANCH_CLEANER_ENABLED"), True),
            enable_intelligence_standardizer=_parse_bool(os.getenv("INTELLIGENCE_AGENT_ENABLED"), True),
            enable_ai=enable_ai,
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
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        )
