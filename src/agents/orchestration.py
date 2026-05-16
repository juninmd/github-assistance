"""
Agent orchestration and coordination utilities.
Provides tools for managing agent execution order, dependencies, and coordination.
"""
from enum import Enum


class AgentPriority(Enum):
    """Priority levels for agent execution."""
    CRITICAL = 1  # Security Scanner, Secret Remover
    HIGH = 2      # PR Assistant, CI Health
    MEDIUM = 3    # Senior Developer, Jules Tracker
    LOW = 4       # Product Manager, Project Creator


class AgentDependency:
    """
    Represents a dependency between agents.
    Some agents should run after others (e.g., Secret Remover after Security Scanner).
    """

    def __init__(self, agent_name: str, depends_on: list[str] | None = None):
        self.agent_name = agent_name
        self.depends_on = depends_on or []

    def can_run(self, completed_agents: set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in completed_agents for dep in self.depends_on)


class AgentOrchestrator:
    """
    Orchestrates agent execution with dependencies and priorities.
    Ensures agents run in the correct order and respects priorities.
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
        """Register an agent with its priority and dependencies."""
        self.dependencies[agent_name] = AgentDependency(agent_name, depends_on)
        self.priorities[agent_name] = priority

    def get_execution_order(self, agents: list[str]) -> list[str]:
        """
        Calculate the optimal execution order for the given agents.
        Respects dependencies and prioritizes by priority level.
        Uses O(n) set operations instead of O(n²) list removals.
        """
        completed: set[str] = set()
        ordered: list[str] = []
        remaining: set[str] = set(agents)

        while remaining:
            # Find agents that can run (all dependencies satisfied)
            ready = [
                agent for agent in remaining
                if agent not in self.dependencies
                or self.dependencies[agent].can_run(completed)
            ]

            if not ready:
                # Circular dependency detected or missing dependency
                ordered.extend(remaining)
                break

            # Sort ready agents by priority
            ready.sort(key=lambda a: self.priorities.get(a, AgentPriority.MEDIUM).value)

            # Add the highest priority ready agent to the order
            next_agent = ready[0]
            ordered.append(next_agent)
            completed.add(next_agent)
            remaining.discard(next_agent)

        return ordered

    def get_parallel_batches(self, agents: list[str]) -> list[list[str]]:
        """
        Group agents into batches that can run in parallel.
        Agents in the same batch have no dependencies on each other.
        Uses O(n) set operations instead of O(n²) list removals.
        """
        completed: set[str] = set()
        batches: list[list[str]] = []
        remaining: set[str] = set(agents)

        while remaining:
            # Find all agents that can run now
            ready = [
                agent for agent in remaining
                if agent not in self.dependencies
                or self.dependencies[agent].can_run(completed)
            ]

            if not ready:
                # Add remaining agents to a final batch (circular dependency or missing dep)
                batches.append(list(remaining))
                break

            # All ready agents can run in parallel
            batches.append(ready)
            completed.update(ready)
            remaining.difference_update(ready)

        return batches


# Default orchestrator with standard agent configuration
def create_default_orchestrator() -> AgentOrchestrator:
    """Create an orchestrator with default agent priorities and dependencies."""
    orchestrator = AgentOrchestrator()

    # Critical priority agents (security)
    orchestrator.register_agent("security-scanner", AgentPriority.CRITICAL)
    orchestrator.register_agent(
        "secret-remover",
        AgentPriority.CRITICAL,
        depends_on=["security-scanner"],
    )

    # High priority agents (blocking issues)
    orchestrator.register_agent("pr-assistant", AgentPriority.HIGH)
    orchestrator.register_agent("ci-health", AgentPriority.HIGH)
    orchestrator.register_agent("conflict-resolver", AgentPriority.HIGH)
    orchestrator.register_agent("code-reviewer", AgentPriority.HIGH)

    # Medium priority agents (improvements)
    orchestrator.register_agent("senior-developer", AgentPriority.MEDIUM)
    orchestrator.register_agent("jules-tracker", AgentPriority.MEDIUM)

    # Low priority agents (planning)
    orchestrator.register_agent("product-manager", AgentPriority.LOW)
    orchestrator.register_agent("interface-developer", AgentPriority.LOW)
    orchestrator.register_agent("project-creator", AgentPriority.LOW)
    orchestrator.register_agent("pr-sla", AgentPriority.LOW)

    return orchestrator
