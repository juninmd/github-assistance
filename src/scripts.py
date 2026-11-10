"""Console entry points: one per agent, generated from the agent catalog.

``pyproject.toml`` maps e.g. ``pr-assistant = "src.scripts:pr_assistant"``; the
callables are resolved lazily so a new catalog entry needs no code here.
"""

from collections.abc import Callable

from src.agents.core.catalog import AGENT_CATALOG
from src.config.settings import Settings
from src.run_agent import run_agent, run_all

_ENTRY_POINTS = {spec.package: spec.name for spec in AGENT_CATALOG}


def _run(agent_name: str) -> None:
    settings = Settings.from_env()
    if agent_name == "all":
        run_all(settings)
    else:
        run_agent(agent_name, settings)


def all_agents() -> None:
    _run("all")


def __getattr__(name: str) -> Callable[[], None]:
    agent_name = _ENTRY_POINTS.get(name)
    if agent_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def entry_point() -> None:
        _run(agent_name)

    entry_point.__name__ = name
    return entry_point


def __dir__() -> list[str]:
    return sorted([*globals(), *_ENTRY_POINTS])
