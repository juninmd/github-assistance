"""
Application settings and configuration.
"""

import os
from dataclasses import dataclass
from typing import Self

from dotenv import load_dotenv

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}

DEFAULT_MODELS = {
    "litellm": "cloud/llama-70b",
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
    enable_pr_sla: bool = True
    enable_jules_tracker: bool = True
    enable_secret_remover: bool = True
    enable_project_creator: bool = True
    enable_branch_cleaner: bool = True
    enable_intelligence_standardizer: bool = True
    enable_readme_curator: bool = True
    enable_ai: bool = False

    # Repository Configuration
    repository_allowlist_path: str = "config/repositories.json"

    # AI Configuration (all traffic via the cluster LiteLLM proxy)
    litellm_api_key: str | None = None
    litellm_api_base: str = "https://litellm.antonio-code.duckdns.org/v1"
    ai_provider: str = "litellm"
    ai_model: str = "cloud/llama-70b"

    # Telegram
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # GitHub App webhook service
    github_app_id: int | None = None
    github_installation_id: int | None = None
    github_app_private_key_path: str | None = None
    github_webhook_secret: str | None = None
    webhook_database_path: str = "data/webhooks.db"
    automation_mode: str = "observe"

    @classmethod
    def _resolve_ai_config(cls, enable_ai: bool) -> tuple[str, str]:
        """All AI traffic goes through the OpenAI-compatible LiteLLM proxy on the cluster."""
        model_env = os.getenv("AI_MODEL")
        ai_model = (model_env or DEFAULT_MODELS["litellm"]).strip() or DEFAULT_MODELS["litellm"]
        return "litellm", ai_model

    @classmethod
    def from_env(cls) -> Self:
        load_dotenv()
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")

        enable_ai = _parse_bool(os.getenv("ENABLE_AI"), False)
        provider, ai_model = cls._resolve_ai_config(enable_ai)

        return cls(
            github_token=github_token,
            github_owner=os.getenv("GITHUB_OWNER", "juninmd"),
            jules_api_key=os.getenv("JULES_API_KEY"),
            enable_product_manager=_parse_bool(os.getenv("PM_AGENT_ENABLED"), True),
            enable_interface_developer=_parse_bool(os.getenv("UI_AGENT_ENABLED"), True),
            enable_senior_developer=_parse_bool(os.getenv("DEV_AGENT_ENABLED"), True),
            enable_pr_assistant=_parse_bool(os.getenv("PR_ASSISTANT_ENABLED"), True),
            enable_security_scanner=_parse_bool(os.getenv("SECURITY_SCANNER_ENABLED"), True),
            enable_ci_health=_parse_bool(os.getenv("CI_HEALTH_ENABLED"), True),
            enable_pr_sla=_parse_bool(os.getenv("PR_SLA_ENABLED"), True),
            enable_jules_tracker=_parse_bool(os.getenv("JULES_TRACKER_ENABLED"), True),
            enable_secret_remover=_parse_bool(os.getenv("SECRET_REMOVER_ENABLED"), True),
            enable_project_creator=_parse_bool(os.getenv("PROJECT_CREATOR_ENABLED"), True),
            enable_branch_cleaner=_parse_bool(os.getenv("BRANCH_CLEANER_ENABLED"), True),
            enable_intelligence_standardizer=_parse_bool(
                os.getenv("INTELLIGENCE_AGENT_ENABLED"), True
            ),
            enable_readme_curator=_parse_bool(os.getenv("README_CURATOR_ENABLED"), True),
            enable_ai=enable_ai,
            repository_allowlist_path=os.getenv(
                "REPOSITORY_ALLOWLIST_PATH", "config/repositories.json"
            ),
            litellm_api_key=os.getenv("LITELLM_API_KEY"),
            litellm_api_base=os.getenv(
                "LITELLM_API_BASE", "https://litellm.antonio-code.duckdns.org/v1"
            ),
            ai_provider=provider,
            ai_model=ai_model,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("telegram_bot_token"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or os.getenv("telegram_chat_id"),
            github_app_id=_optional_int(os.getenv("GITHUB_APP_ID"), "GITHUB_APP_ID"),
            github_installation_id=_optional_int(
                os.getenv("GITHUB_INSTALLATION_ID"), "GITHUB_INSTALLATION_ID"
            ),
            github_app_private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
            github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET"),
            webhook_database_path=os.getenv("WEBHOOK_DATABASE_PATH", "data/webhooks.db"),
            automation_mode=os.getenv("AUTOMATION_MODE", "observe").strip().lower(),
        )


def _optional_int(value: str | None, env_name: str) -> int | None:
    if value is None:
        return None
    return _parse_positive_int(value, 1, env_name)
