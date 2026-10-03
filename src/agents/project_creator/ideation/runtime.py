"""Wires config, memory, GitHub signals, search and critic into one ideation run."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.ai import get_ai_client

from .config import IdeationConfig
from .feedback import collect_signals
from .memory import IdeaMemory
from .pipeline import IdeationPipeline
from .similar import make_searcher


def run_ideation(
    generate: Callable[[str], str],
    github_client: Any,
    history: list[str],
    names: list[str],
    notice: str,
    log: Callable[..., None],
    config: IdeationConfig | None = None,
) -> dict[str, Any] | None:
    cfg = config or IdeationConfig.from_env()
    try:
        repos = github_client.get_user_repos(sort="created", limit=100)
    except Exception as exc:
        log(f"Could not load repos for outcome feedback: {exc}", "WARNING")
        repos = []
    signals = collect_signals(repos, notice, log)
    memory = IdeaMemory(cfg.memory_path, log)
    signals.recent += memory.recent_choices()
    signals.rejected = memory.rejected_names()
    critic = None
    if cfg.critic_model:
        critic = get_ai_client(provider="litellm", model=cfg.critic_model).generate
    search = make_searcher(github_client, log) if cfg.similar_search else None
    pipeline = IdeationPipeline(
        generate, log, config=cfg, critic=critic, search=search, signals=signals
    )
    idea = pipeline.run(history, names)
    memory.record(pipeline.report)
    return idea
