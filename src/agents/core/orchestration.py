"""
Agent orchestration and coordination utilities.
Provides tools for managing agent execution order, dependencies, and coordination.
"""

from __future__ import annotations

from src.agents.core.catalog import AGENT_CATALOG, AgentPriority

__all__ = ["AgentDependency", "AgentOrchestrator", "AgentPriority", "create_default_orchestrator"]


class AgentDependency:
    """A dependency between agents (e.g. Secret Remover after Security Scanner)."""

    def __init__(self, agent_name: str, depends_on: list[str] | None = None):
        self.agent_name = agent_name
        self.depends_on = depends_on or []

    def can_run(self, completed_agents: set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in completed_agents for dep in self.depends_on)


class AgentOrchestrator:
    """Orchestrates agents with dependencies and priorities.

    Cycles and missing dependencies are rejected loudly instead of being
    silently appended, because dependents must only run after real success.
    """

    def __init__(self):
        self.dependencies: dict[str, AgentDependency] = {}
        self.priorities: dict[str, AgentPriority] = {}

    def register_agent(
        self,
        agent_name: str,
        priority: AgentPriority = AgentPriority.MEDIUM,
        depends_on: list[str] | None = None,
    ) -> None:
        self.dependencies[agent_name] = AgentDependency(agent_name, depends_on)
        self.priorities[agent_name] = priority

    def validate(self, agents: list[str]) -> None:
        """Reject missing dependencies and dependency cycles loudly."""
        registered = set(self.dependencies)
        missing = {
            dep
            for agent in agents
            for dep in (self.dependencies[agent].depends_on if agent in self.dependencies else [])
            if dep not in registered
        }
        if missing:
            raise ValueError(
                f"missing dependencies: {', '.join(sorted(missing))} are not registered"
            )
        completed: set[str] = set()
        remaining: set[str] = set(agents)
        while remaining:
            ready = [
                agent
                for agent in remaining
                if agent not in self.dependencies
                or self.dependencies[agent].can_run(completed)
            ]
            if not ready:
                if not self._external_deps(remaining):
                    raise ValueError(
                        f"circular dependency detected among: {sorted(remaining)}"
                    )
                break
            ready.sort(key=lambda a: self.priorities.get(a, AgentPriority.MEDIUM).value)
            completed.add(ready[0])
            remaining.discard(ready[0])

    def _external_deps(self, remaining: set[str]) -> bool:
        """True when every unmet dependency of the remaining agents is outside the set.

        A dependent whose dependency is not part of this run is not a cycle: the
        runner blocks it when the dependency never succeeded.
        """
        for agent in remaining:
            deps = self.dependencies[agent].depends_on if agent in self.dependencies else []
            if any(dep in remaining for dep in deps):
                return False
        return True

    def get_execution_order(self, agents: list[str]) -> list[str]:
        """Respect dependencies and prioritize by priority level."""
        self.validate(agents)
        completed: set[str] = set()
        ordered: list[str] = []
        remaining: set[str] = set(agents)
        while remaining:
            ready = [
                agent
                for agent in remaining
                if agent not in self.dependencies
                or self.dependencies[agent].can_run(completed)
            ]
            if not ready:
                if self._external_deps(remaining):
                    ordered.extend(sorted(remaining))
                else:
                    raise ValueError(f"circular dependency detected among: {sorted(remaining)}")
                break
            ready.sort(key=lambda a: self.priorities.get(a, AgentPriority.MEDIUM).value)
            next_agent = ready[0]
            ordered.append(next_agent)
            completed.add(next_agent)
            remaining.discard(next_agent)
        return ordered

    def get_parallel_batches(self, agents: list[str]) -> list[list[str]]:
        """Group agents into batches; same-batch agents have no dependency."""
        self.validate(agents)
        completed: set[str] = set()
        batches: list[list[str]] = []
        remaining: set[str] = set(agents)
        while remaining:
            ready = [
                agent
                for agent in agents
                if agent in remaining
                and (
                    agent not in self.dependencies
                    or self.dependencies[agent].can_run(completed)
                )
            ]
            if not ready:
                if self._external_deps(remaining):
                    batches.append(sorted(remaining))
                else:
                    raise ValueError(f"circular dependency detected among: {sorted(remaining)}")
                break
            batches.append(ready)
            completed.update(ready)
            remaining.difference_update(ready)
        return batches


def create_default_orchestrator() -> AgentOrchestrator:
    """Create an orchestrator from the agent catalog (priorities and dependencies)."""
    orchestrator = AgentOrchestrator()
    for spec in AGENT_CATALOG:
        orchestrator.register_agent(spec.name, spec.priority, depends_on=list(spec.depends_on))
    return orchestrator
