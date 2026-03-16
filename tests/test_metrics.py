"""Tests for agent metrics module."""
import unittest
from datetime import UTC, datetime

from src.agents.metrics import AgentMetrics


class TestAgentMetrics(unittest.TestCase):
    def test_init(self):
        metrics = AgentMetrics("test-agent")
        self.assertEqual(metrics.agent_name, "test-agent")
        self.assertIsInstance(metrics.start_time, datetime)
        self.assertEqual(metrics.metrics["items_processed"], 0)
        self.assertEqual(metrics.metrics["items_failed"], 0)

    def test_increment_processed(self):
        metrics = AgentMetrics("test-agent")
        metrics.increment_processed()
        self.assertEqual(metrics.metrics["items_processed"], 1)
        metrics.increment_processed(5)
        self.assertEqual(metrics.metrics["items_processed"], 6)

    def test_increment_failed(self):
        metrics = AgentMetrics("test-agent")
        metrics.increment_failed()
        self.assertEqual(metrics.metrics["items_failed"], 1)
        metrics.increment_failed(3)
        self.assertEqual(metrics.metrics["items_failed"], 4)

    def test_record_github_api_call(self):
        metrics = AgentMetrics("test-agent")
        metrics.record_github_api_call()
        self.assertEqual(metrics.metrics["github_api_calls"], 1)
        metrics.record_github_api_call()
        self.assertEqual(metrics.metrics["github_api_calls"], 2)

    def test_record_jules_session(self):
        metrics = AgentMetrics("test-agent")
        metrics.record_jules_session()
        self.assertEqual(metrics.metrics["jules_sessions_created"], 1)

    def test_add_error(self):
        metrics = AgentMetrics("test-agent")
        metrics.add_error("Test error")
        self.assertEqual(len(metrics.metrics["errors"]), 1)
        self.assertEqual(metrics.metrics["errors"][0]["message"], "Test error")

    def test_add_warning(self):
        metrics = AgentMetrics("test-agent")
        metrics.add_warning("Test warning")
        self.assertEqual(len(metrics.metrics["warnings"]), 1)
        self.assertEqual(metrics.metrics["warnings"][0]["message"], "Test warning")

    def test_finalize(self):
        metrics = AgentMetrics("test-agent")
        metrics.increment_processed(10)
        metrics.increment_failed(2)
        metrics.add_error("Error 1")
        metrics.add_warning("Warning 1")

        result = metrics.finalize()

        self.assertEqual(result["items_processed"], 10)
        self.assertEqual(result["items_failed"], 2)
        self.assertEqual(result["total_items"], 12)
        self.assertAlmostEqual(result["success_rate"], 83.33, places=2)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["warning_count"], 1)
        self.assertIn("duration_seconds", result)
        self.assertIn("execution_end", result)

    def test_finalize_no_items(self):
        metrics = AgentMetrics("test-agent")
        result = metrics.finalize()
        self.assertEqual(result["success_rate"], 100.0)
        self.assertEqual(result["total_items"], 0)

    def test_get_summary(self):
        metrics = AgentMetrics("test-agent")
        metrics.increment_processed(5)
        metrics.increment_failed(1)
        metrics.add_error("Test error")
        metrics.add_warning("Test warning")

        summary = metrics.get_summary()

        self.assertIn("test-agent", summary)
        self.assertIn("Processed: 5", summary)
        self.assertIn("Failed: 1", summary)
        self.assertIn("Success Rate:", summary)
        self.assertIn("Errors: 1", summary)
        self.assertIn("Warnings: 1", summary)
