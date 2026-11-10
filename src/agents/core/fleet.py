"""Fleet view: the agent catalog joined with the live ``Settings`` toggles."""

from __future__ import annotations

from typing import Any

from src.agents.core.catalog import AGENT_CATALOG, AgentSpec
from src.config.settings import Settings


def _blocked_reason(spec: AgentSpec, settings: Settings) -> str | None:
    """Why the agent would not run right now, or ``None`` when it can."""
    if spec.toggle_attr and not getattr(settings, spec.toggle_attr):
        return f"{spec.toggle_env}=false"
    if spec.requires_ai and not settings.enable_ai:
        return "ENABLE_AI=false"
    if spec.uses_jules and not settings.jules_api_key:
        return "JULES_API_KEY ausente"
    return None


def fleet_status(settings: Settings) -> dict[str, Any]:
    """Describe every agent and whether the current configuration lets it run."""
    agents = []
    for spec in AGENT_CATALOG:
        reason = _blocked_reason(spec, settings)
        agents.append(
            {
                "name": spec.name,
                "emoji": spec.emoji,
                "summary": spec.summary,
                "priority": spec.priority.name.lower(),
                "requires_ai": spec.requires_ai,
                "uses_jules": spec.uses_jules,
                "notifies_telegram": spec.notifies_telegram,
                "accepts_pr_ref": spec.accepts_pr_ref,
                "depends_on": list(spec.depends_on),
                "in_batch": spec.in_batch,
                "toggle_env": spec.toggle_env,
                "runnable": reason is None,
                "blocked_reason": reason,
            }
        )
    return {
        "agents": agents,
        "ai": {
            "enabled": settings.enable_ai,
            "provider": settings.ai_provider,
            "model": settings.ai_model,
        },
        "owner": settings.github_owner,
    }
