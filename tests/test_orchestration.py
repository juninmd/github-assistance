"""Tests for agent orchestration module."""
import unittest

from src.agents.orchestration import (
    AgentDependency,
    AgentOrchestrator,
    AgentPriority,
    create_default_orchestrator,
)


class TestAgentDependency(unittest.TestCase):
    def test_init(self):
        dep = AgentDependency("agent1", ["agent2", "agent3"])
        self.assertEqual(dep.agent_name, "agent1")
        self.assertEqual(dep.depends_on, ["agent2", "agent3"])

    def test_init_no_dependencies(self):
        dep = AgentDependency("agent1")
        self.assertEqual(dep.depends_on, [])

    def test_can_run_satisfied(self):
        dep = AgentDependency("agent1", ["agent2", "agent3"])
        completed = {"agent2", "agent3", "agent4"}
        self.assertTrue(dep.can_run(completed))

    def test_can_run_not_satisfied(self):
        dep = AgentDependency("agent1", ["agent2", "agent3"])
        completed = {"agent2"}
        self.assertFalse(dep.can_run(completed))

    def test_can_run_no_dependencies(self):
        dep = AgentDependency("agent1")
        self.assertTrue(dep.can_run(set()))


class TestAgentOrchestrator(unittest.TestCase):
    def test_register_agent(self):
        orch = AgentOrchestrator()
        orch.register_agent("agent1", AgentPriority.HIGH, ["agent2"])

        self.assertIn("agent1", orch.dependencies)
        self.assertEqual(orch.priorities["agent1"], AgentPriority.HIGH)

    def test_get_execution_order_no_dependencies(self):
        orch = AgentOrchestrator()
        orch.register_agent("agent1", AgentPriority.HIGH)
        orch.register_agent("agent2", AgentPriority.MEDIUM)
        orch.register_agent("agent3", AgentPriority.CRITICAL)

        order = orch.get_execution_order(["agent1", "agent2", "agent3"])

        # Should be sorted by priority
        self.assertEqual(order[0], "agent3")  # CRITICAL
        self.assertEqual(order[1], "agent1")  # HIGH
        self.assertEqual(order[2], "agent2")  # MEDIUM

    def test_get_execution_order_with_dependencies(self):
        orch = AgentOrchestrator()
        orch.register_agent("agent1", AgentPriority.HIGH)
        orch.register_agent("agent2", AgentPriority.CRITICAL, ["agent1"])

        order = orch.get_execution_order(["agent1", "agent2"])

        # agent1 must come before agent2 despite lower priority
        self.assertEqual(order, ["agent1", "agent2"])

    def test_get_execution_order_complex(self):
        orch = AgentOrchestrator()
        orch.register_agent("a", AgentPriority.MEDIUM)
        orch.register_agent("b", AgentPriority.HIGH, ["a"])
        orch.register_agent("c", AgentPriority.CRITICAL, ["b"])
        orch.register_agent("d", AgentPriority.LOW)

        order = orch.get_execution_order(["a", "b", "c", "d"])

        # Dependencies: c->b->a, d independent
        # Expected: a, b, c, d (or d, a, b, c - d can be anywhere)
        self.assertEqual(order.index("a") < order.index("b"), True)
        self.assertEqual(order.index("b") < order.index("c"), True)

    def test_get_execution_order_circular_dependency(self):
        orch = AgentOrchestrator()
        orch.register_agent("a", AgentPriority.MEDIUM, ["b"])
        orch.register_agent("b", AgentPriority.MEDIUM, ["a"])

        order = orch.get_execution_order(["a", "b"])
        # With circular dependency, it should just return the remaining
        self.assertEqual(set(order), {"a", "b"})

    def test_get_parallel_batches_no_dependencies(self):
        orch = AgentOrchestrator()
        orch.register_agent("agent1")
        orch.register_agent("agent2")
        orch.register_agent("agent3")

        batches = orch.get_parallel_batches(["agent1", "agent2", "agent3"])

        # All can run in parallel
        self.assertEqual(len(batches), 1)
        self.assertEqual(set(batches[0]), {"agent1", "agent2", "agent3"})

    def test_get_parallel_batches_with_dependencies(self):
        orch = AgentOrchestrator()
        orch.register_agent("agent1")
        orch.register_agent("agent2", depends_on=["agent1"])
        orch.register_agent("agent3", depends_on=["agent1"])

        batches = orch.get_parallel_batches(["agent1", "agent2", "agent3"])

        # First batch: agent1
        # Second batch: agent2, agent3 (parallel)
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0], ["agent1"])
        self.assertEqual(set(batches[1]), {"agent2", "agent3"})

    def test_get_parallel_batches_chain(self):
        orch = AgentOrchestrator()
        orch.register_agent("a")
        orch.register_agent("b", depends_on=["a"])
        orch.register_agent("c", depends_on=["b"])

        batches = orch.get_parallel_batches(["a", "b", "c"])

        # Must run sequentially
        self.assertEqual(len(batches), 3)
        self.assertEqual(batches[0], ["a"])
        self.assertEqual(batches[1], ["b"])
        self.assertEqual(batches[2], ["c"])

    def test_get_parallel_batches_circular_dependency(self):
        orch = AgentOrchestrator()
        orch.register_agent("a", depends_on=["b"])
        orch.register_agent("b", depends_on=["a"])

        batches = orch.get_parallel_batches(["a", "b"])
        # Should just return remaining in the last batch
        self.assertEqual(len(batches), 1)
        self.assertEqual(set(batches[0]), {"a", "b"})


class TestDefaultOrchestrator(unittest.TestCase):
    def test_create_default_orchestrator(self):
        orch = create_default_orchestrator()

        # Check some key agents are registered
        self.assertIn("security-scanner", orch.dependencies)
        self.assertIn("secret-remover", orch.dependencies)
        self.assertIn("pr-assistant", orch.dependencies)

        # Check priority assignments
        self.assertEqual(orch.priorities["security-scanner"], AgentPriority.CRITICAL)
        self.assertEqual(orch.priorities["pr-assistant"], AgentPriority.HIGH)
        self.assertEqual(orch.priorities["senior-developer"], AgentPriority.MEDIUM)
        self.assertEqual(orch.priorities["product-manager"], AgentPriority.LOW)

    def test_default_orchestrator_dependencies(self):
        orch = create_default_orchestrator()

        # secret-remover should depend on security-scanner
        dep = orch.dependencies["secret-remover"]
        self.assertIn("security-scanner", dep.depends_on)

    def test_default_orchestrator_execution_order(self):
        orch = create_default_orchestrator()

        agents = ["secret-remover", "security-scanner", "pr-assistant"]
        order = orch.get_execution_order(agents)

        # security-scanner must come before secret-remover
        scanner_idx = order.index("security-scanner")
        remover_idx = order.index("secret-remover")
        self.assertLess(scanner_idx, remover_idx)
