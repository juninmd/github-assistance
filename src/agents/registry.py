"""Agent registry and creation logic."""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from src.config.repository_allowlist import RepositoryAllowlist
from src.config.settings import DEFAULT_MODELS, Settings
from src.github_client import GithubClient
from src.jules.client import JulesClient
from src.notifications.telegram import TelegramNotifier

if TYPE_CHECKING:
    from src.agents.base_agent import BaseAgent


_AGENT_IMPORTS: dict[str, str] = {
    "product-manager": "src.agents.product_manager.agent:ProductManagerAgent",
    "interface-developer": "src.agents.interface_developer.agent:InterfaceDeveloperAgent",
    "senior-developer": "src.agents.senior_developer.agent:SeniorDeveloperAgent",
    "pr-assistant": "src.agents.pr_assistant.agent:PRAssistantAgent",
    "security-scanner": "src.agents.security_scanner.agent:SecurityScannerAgent",
    "ci-health": "src.agents.ci_health.agent:CIHealthAgent",
    "pr-sla": "src.agents.pr_sla.agent:PRSLAAgent",
    "jules-tracker": "src.agents.jules_tracker.agent:JulesTrackerAgent",
    "secret-remover": "src.agents.secret_remover.agent:SecretRemoverAgent",
    "project-creator": "src.agents.project_creator.agent:ProjectCreatorAgent",
    "conflict-resolver": "src.agents.conflict_resolver.agent:ConflictResolverAgent",
    "code-reviewer": "src.agents.code_reviewer.agent:CodeReviewerAgent",
    "branch-cleaner": "src.agents.branch_cleaner.agent:BranchCleanerAgent",
    "intelligence-standardizer": "src.agents.intelligence_standardizer.agent:IntelligenceStandardizerAgent",
}


class LazyAgentRegistry:
    """Resolve agent classes only when an agent is actually executed."""

    def __init__(self, imports: dict[str, str]) -> None:
        self._imports = imports
        self._cache: dict[str, type[BaseAgent]] = {}

    def __getitem__(self, name: str) -> type[BaseAgent]:
        if name not in self._imports:
            raise KeyError(name)
        if name not in self._cache:
            module_name, class_name = self._imports[name].split(":", 1)
            module = import_module(module_name)
            self._cache[name] = getattr(module, class_name)
        return self._cache[name]

    def keys(self):
        return self._imports.keys()


AGENT_REGISTRY = LazyAgentRegistry(_AGENT_IMPORTS)

AGENTS_WITH_AI = {
    "product-manager", "interface-developer", "senior-developer",
    "jules-tracker", "secret-remover",
    "project-creator", "code-reviewer",
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

    if agent_name == "pr-assistant":
        kwargs["comment_ai_enabled"] = settings.enable_ai

    if agent_name in ["pr-assistant", "code-reviewer", "conflict-resolver"] and pr_ref:
        kwargs["pr_ref"] = pr_ref

    return agent_cls(**kwargs)
