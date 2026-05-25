"""Pre-flight health checks before agent execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.agents.registry import AGENTS_WITH_AI, AGENTS_WITH_JULES

if TYPE_CHECKING:
    from src.config.settings import Settings


@dataclass
class HealthReport:
    passed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = []
        for p in self.passed:
            lines.append(f"  ✅ {p}")
        for w in self.warnings:
            lines.append(f"  ⚠️  {w}")
        for e in self.errors:
            lines.append(f"  ❌ {e}")
        return "\n".join(lines)


def run_health_checks(settings: Settings, agent_name: str) -> HealthReport:
    """Run pre-flight checks relevant to the requested agent."""
    report = HealthReport()
    is_all = agent_name == "all"

    # GitHub token
    if settings.github_token:
        report.passed.append("GITHUB_TOKEN present")
    else:
        report.errors.append("GITHUB_TOKEN is missing — GitHub operations will fail")

    # Jules key (only needed for session-creating agents)
    if agent_name in AGENTS_WITH_JULES or is_all:
        if settings.jules_api_key:
            report.passed.append("JULES_API_KEY present")
        else:
            report.warnings.append("JULES_API_KEY missing — Jules session creation will be skipped")

    # AI provider key checks
    if settings.enable_ai and (agent_name in AGENTS_WITH_AI or is_all):
        provider = settings.ai_provider
        match provider:
            case "gemini" if not settings.gemini_api_key:
                report.errors.append("AI_PROVIDER=gemini but GEMINI_API_KEY is missing")
            case "openai" if not settings.openai_api_key:
                report.errors.append("AI_PROVIDER=openai but OPENAI_API_KEY is missing")
            case "ollama":
                report.passed.append(f"AI provider: ollama @ {settings.ollama_base_url}")
        if not report.errors:
            report.passed.append(f"AI provider: {provider} / model: {settings.ai_model}")

    # Telegram (optional — just warn)
    if settings.telegram_bot_token and settings.telegram_chat_id:
        report.passed.append("Telegram notifications enabled")
    else:
        report.warnings.append("Telegram credentials missing — notifications will be silent")

    return report
