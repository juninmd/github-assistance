"""Agent registry and creation logic."""
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.branch_cleaner.agent import BranchCleanerAgent
from src.agents.ci_health.agent import CIHealthAgent
from src.agents.code_reviewer.agent import CodeReviewerAgent
from src.agents.conflict_resolver.agent import ConflictResolverAgent
from src.agents.intelligence_standardizer.agent import IntelligenceStandardizerAgent
from src.agents.interface_developer.agent import InterfaceDeveloperAgent
from src.agents.jules_tracker.agent import JulesTrackerAgent
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.agents.pr_sla.agent import PRSLAAgent
from src.agents.product_manager.agent import ProductManagerAgent
from src.agents.project_creator.agent import ProjectCreatorAgent
from src.agents.secret_remover.agent import SecretRemoverAgent
from src.agents.security_scanner.agent import SecurityScannerAgent
from src.agents.senior_developer.agent import SeniorDeveloperAgent
from src.config.repository_allowlist import RepositoryAllowlist
from src.config.settings import DEFAULT_MODELS, Settings
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "product-manager": ProductManagerAgent,
    "interface-developer": InterfaceDeveloperAgent,
    "senior-developer": SeniorDeveloperAgent,
    "pr-assistant": PRAssistantAgent,
    "security-scanner": SecurityScannerAgent,
    "ci-health": CIHealthAgent,
    "pr-sla": PRSLAAgent,
    "jules-tracker": JulesTrackerAgent,
    "secret-remover": SecretRemoverAgent,
    "project-creator": ProjectCreatorAgent,
    "conflict-resolver": ConflictResolverAgent,
    "code-reviewer": CodeReviewerAgent,
    "branch-cleaner": BranchCleanerAgent,
    "intelligence-standardizer": IntelligenceStandardizerAgent,
}

AGENTS_WITH_AI = {
    "product-manager", "interface-developer", "senior-developer",
    "pr-assistant", "jules-tracker", "secret-remover",
    "project-creator", "conflict-resolver", "code-reviewer",
    "intelligence-standardizer"
}


def create_base_deps(settings: Settings) -> dict[str, Any]:
    """Create the shared dependencies every agent needs."""
    return {
        "github_client": GithubClient(settings.github_token),
        "jules_client": JulesClient(settings.jules_api_key),
        "allowlist": RepositoryAllowlist(settings.repository_allowlist_path),
        "telegram": TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        ),
    }


def build_ai_config(settings: Settings, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Build AI config dict from settings with optional overrides."""
    config: dict[str, Any] = {}
    resolved_provider = provider or settings.ai_provider
    resolved_model = model or settings.ai_model

    if provider and not model:
        resolved_model = DEFAULT_MODELS.get(resolved_provider, resolved_model)

    match resolved_provider:
        case "gemini":
            config["api_key"] = settings.gemini_api_key
        case "openai":
            config["api_key"] = settings.openai_api_key
        case "ollama":
            config["base_url"] = settings.ollama_base_url

    return {"ai_provider": resolved_provider, "ai_model": resolved_model, "ai_config": config}


def create_agent(
    agent_name: str,
    settings: Settings,
    provider: str | None = None,
    model: str | None = None,
    pr_ref: str | None = None,
) -> BaseAgent:
    """Instantiate any agent by name with all dependencies."""
    agent_cls = AGENT_REGISTRY[agent_name]
    deps = create_base_deps(settings)
    kwargs: dict[str, Any] = {**deps}

    kwargs["telegram"] = TelegramNotifier(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        prefix=f"[{agent_name.replace('-', ' ').upper()}]"
    )
    kwargs["target_owner"] = settings.github_owner

    if agent_name in AGENTS_WITH_AI:
        if not settings.enable_ai:
            raise PermissionError(f"Agent '{agent_name}' requires AI but ENABLE_AI is false.")
        kwargs.update(build_ai_config(settings, provider, model))

    if agent_name in ["pr-assistant", "code-reviewer", "conflict-resolver"] and pr_ref:
        kwargs["pr_ref"] = pr_ref

    return agent_cls(**kwargs)
