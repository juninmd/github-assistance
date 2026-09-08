"""Typed execution-result contract for agents and the durable queue.

Item counts are derived from *lists* of items, never from dict keys, so
``len({"done": {...}})`` is not counted as one finished item. Cost is only
recorded when the caller actually knows it — never invented.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from src.utils.logger import new_correlation_id


def item_count(value: Any) -> int:
    """Count items in list-like containers only (dict keys are not items)."""
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 0


@dataclass
class RunResult:
    agent: str
    task_id: str = field(default_factory=lambda: new_correlation_id() or uuid.uuid4().hex[:8])
    repo: str | None = None
    pr_ref: str | None = None
    sha: str | None = None
    status: str = "succeeded"  # succeeded | failed | blocked | skipped
    items_done: int = 0
    items_failed: int = 0
    items_skipped: int = 0
    items_blocked: int = 0
    duration_seconds: float = 0.0
    api_calls: int = 0
    cost: float | None = None  # never invented
    attempts: int = 0
    decision: str | None = None
    next_action: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def from_agent_dict(
        cls, agent: str, data: dict[str, Any], *, task_id: str | None = None
    ) -> RunResult:
        """Build a RunResult from a raw agent result dict."""
        skipped = data.get("skipped", [])
        blocked = data.get("blocked", [])
        failed = data.get("failed", data.get("pipeline_failures", []))
        done = data.get("merged", data.get("processed", data.get("resolved", [])))
        status = "succeeded"
        if data.get("error"):
            status = "failed"
        elif blocked:
            status = "blocked"
        elif failed:
            status = "failed"
        return cls(
            agent=agent,
            task_id=task_id or uuid.uuid4().hex[:8],
            repo=data.get("repository") or data.get("repo"),
            pr_ref=data.get("pr_ref"),
            sha=data.get("sha"),
            status=status,
            items_done=item_count(done),
            items_failed=item_count(failed),
            items_skipped=item_count(skipped),
            items_blocked=item_count(blocked),
            duration_seconds=float(data.get("duration_seconds") or 0.0),
            api_calls=int(data.get("api_calls") or 0),
            cost=data.get("cost"),
            attempts=int(data.get("attempts") or 0),
            decision=data.get("decision"),
            next_action=data.get("next_action"),
            evidence=data.get("evidence", []) if isinstance(data.get("evidence", []), list) else [],
            error=data.get("error"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
