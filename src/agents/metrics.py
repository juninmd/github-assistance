"""
Agent metrics collection and tracking system.
Provides utilities for agents to track performance metrics and KPIs.
"""
from datetime import UTC, datetime
from typing import Any


class AgentMetrics:
    """
    Metrics tracker for agent execution.
    Collects KPIs like execution frequency, success rate, items processed, etc.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.start_time = datetime.now(UTC)
        self.metrics: dict[str, Any] = {
            "agent_name": agent_name,
            "execution_start": self.start_time.isoformat(),
            "items_processed": 0,
            "items_failed": 0,
            "github_api_calls": 0,
            "jules_sessions_created": 0,
            "errors": [],
            "warnings": [],
        }

    def increment_processed(self, count: int = 1) -> None:
        """Increment the count of successfully processed items."""
        self.metrics["items_processed"] += count

    def increment_failed(self, count: int = 1) -> None:
        """Increment the count of failed items."""
        self.metrics["items_failed"] += count

    def record_github_api_call(self) -> None:
        """Record a GitHub API call."""
        self.metrics["github_api_calls"] += 1

    def record_jules_session(self) -> None:
        """Record a Jules session creation."""
        self.metrics["jules_sessions_created"] += 1

    def add_error(self, error: str) -> None:
        """Add an error message to the metrics."""
        self.metrics["errors"].append({"timestamp": datetime.now(UTC).isoformat(), "message": error})

    def add_warning(self, warning: str) -> None:
        """Add a warning message to the metrics."""
        self.metrics["warnings"].append({"timestamp": datetime.now(UTC).isoformat(), "message": warning})

    def finalize(self) -> dict[str, Any]:
        """
        Finalize metrics collection and return the complete metrics dict.
        Calculates duration, success rate, and other derived metrics.
        """
        end_time = datetime.now(UTC)
        duration = (end_time - self.start_time).total_seconds()

        total_items = self.metrics["items_processed"] + self.metrics["items_failed"]
        success_rate = (
            (self.metrics["items_processed"] / total_items * 100) if total_items > 0 else 100.0
        )

        self.metrics.update({
            "execution_end": end_time.isoformat(),
            "duration_seconds": duration,
            "success_rate": round(success_rate, 2),
            "total_items": total_items,
            "error_count": len(self.metrics["errors"]),
            "warning_count": len(self.metrics["warnings"]),
        })

        return self.metrics

    def get_summary(self) -> str:
        """Get a human-readable summary of the metrics."""
        metrics = self.finalize()
        lines = [
            f"📊 Agent Metrics Summary: {self.agent_name}",
            f"⏱️  Duration: {metrics['duration_seconds']:.2f}s",
            f"✅ Processed: {metrics['items_processed']}",
            f"❌ Failed: {metrics['items_failed']}",
            f"📈 Success Rate: {metrics['success_rate']}%",
            f"🔗 GitHub API Calls: {metrics['github_api_calls']}",
            f"🤖 Jules Sessions: {metrics['jules_sessions_created']}",
        ]
        if metrics["error_count"] > 0:
            lines.append(f"⚠️  Errors: {metrics['error_count']}")
        if metrics["warning_count"] > 0:
            lines.append(f"⚠️  Warnings: {metrics['warning_count']}")
        return "\n".join(lines)
