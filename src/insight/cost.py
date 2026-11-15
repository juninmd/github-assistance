"""Per-agent LLM cost ledger: JSONL append on every agent run, summary on demand.

Enabled by ``AI_USAGE_LOG=<path>``. Token figures are estimates (see ``ai/usage.py``).
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


def record_run(metrics: dict[str, Any]) -> None:
    """Append one run's usage; never raises (observability must not break agents)."""
    path = os.getenv("AI_USAGE_LOG")
    if not path or not metrics.get("llm_calls", 0) + metrics.get("llm_cache_hits", 0):
        return
    row = {
        "ts": round(time.time()),
        "agent": metrics.get("agent_name"),
        "calls": metrics.get("llm_calls", 0),
        "cache_hits": metrics.get("llm_cache_hits", 0),
        "tokens_in": metrics.get("llm_tokens_in_est", 0),
        "tokens_out": metrics.get("llm_tokens_out_est", 0),
        "tokens_saved": metrics.get("llm_tokens_saved_est", 0),
    }
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def record_trace(trace: Any) -> None:
    """Append one opencode run (harness, model, skills actually invoked); never raises."""
    path = os.getenv("AI_USAGE_LOG")
    if not path:
        return
    row = {
        "ts": round(time.time()),
        "agent": "opencode",
        "harness": trace.harness,
        "model": trace.model,
        "skills_used": list(trace.skills_used),
        "skills_available": len(trace.skills_available),
        "tokens_in": trace.tokens_in,
        "tokens_out": trace.tokens_out,
        "cost": trace.cost,
        "tokenix": "tokenix" in (trace.harness or ""),
        "tokenix_calls": sum(1 for t in trace.tools if t.startswith("tokenix_")),
        "calls": 1,
    }
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def summarize_skills(path: str, since_hours: float | None = None) -> list[dict[str, Any]]:
    """Per (harness, skill) invocation counts from opencode runs, most used first."""
    cutoff = time.time() - since_hours * 3600 if since_hours else 0
    counts: dict[tuple[str, str], int] = defaultdict(int)
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("ts", 0) < cutoff or "harness" not in row:
            continue
        for skill in row.get("skills_used") or ["(nenhuma)"]:
            counts[(row["harness"] or "?", skill)] += 1
    ranked = [{"harness": h, "skill": s, "runs": n} for (h, s), n in counts.items()]
    return sorted(ranked, key=lambda r: r["runs"], reverse=True)


def summarize(path: str, since_hours: float | None = None) -> list[dict[str, Any]]:
    """Aggregate the ledger per agent, most expensive first."""
    cutoff = time.time() - since_hours * 3600 if since_hours else 0
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"runs": 0, "calls": 0, "cache_hits": 0, "tokens": 0, "tokens_saved": 0}
    )
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("ts", 0) < cutoff:
            continue
        t = totals[row.get("agent") or "?"]
        t["runs"] += 1
        t["calls"] += row.get("calls", 0)
        t["cache_hits"] += row.get("cache_hits", 0)
        t["tokens"] += row.get("tokens_in", 0) + row.get("tokens_out", 0)
        t["tokens_saved"] += row.get("tokens_saved", 0)
    ranked = [{"agent": a, **v} for a, v in totals.items()]
    return sorted(ranked, key=lambda r: r["tokens"], reverse=True)


def summarize_tokenix(path: str, since_hours: float | None = None) -> dict[str, dict[str, float]]:
    """opencode runs with vs without tokenix: runs, mean tokens/run, tokenix tool calls.

    Rows come from :func:`record_trace`; a run counts as "with" when the harness
    label carried tokenix. Compare ``mean_tokens`` between the two groups.
    """
    cutoff = time.time() - since_hours * 3600 if since_hours else 0
    groups = {name: {"runs": 0, "tokens": 0, "tokenix_calls": 0} for name in ("with", "without")}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("ts", 0) < cutoff or "harness" not in row:
            continue
        g = groups["with" if row.get("tokenix") else "without"]
        g["runs"] += 1
        g["tokens"] += row.get("tokens_in", 0) + row.get("tokens_out", 0)
        g["tokenix_calls"] += row.get("tokenix_calls", 0)
    return {
        name: {**g, "mean_tokens": round(g["tokens"] / g["runs"], 1) if g["runs"] else 0.0}
        for name, g in groups.items()
    }
