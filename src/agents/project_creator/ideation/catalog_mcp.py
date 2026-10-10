"""Minimal stdio MCP client for the `catalogo` server, used to avoid duplicate project ideas."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Callable
from typing import Any

ENV_COMMAND = "CATALOG_MCP_COMMAND"  # e.g. "node /path/to/catalogo/scripts/mcp.mjs"
_TIMEOUT = 30


def _rpc(proc: subprocess.Popen, msg_id: int, method: str, params: dict | None = None) -> Any:
    request = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
    proc.stdin.write(json.dumps(request) + "\n")  # type: ignore[union-attr]
    proc.stdin.flush()  # type: ignore[union-attr]
    while True:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if not line:
            raise RuntimeError("catalog MCP server closed the connection")
        reply = json.loads(line)
        if reply.get("id") == msg_id:
            if "error" in reply:
                raise RuntimeError(reply["error"].get("message", "MCP error"))
            return reply["result"]


def fetch_catalog_repos(log: Callable[..., None], command: str | None = None) -> list[dict]:
    """Return the catalog entries (name, purpose, categories, ...); [] when unavailable."""
    command = command or os.getenv(ENV_COMMAND, "").strip()
    if not command:
        log(f"{ENV_COMMAND} not set; skipping catalog duplicate check", "WARNING")
        return []
    try:
        proc = subprocess.Popen(  # noqa: S603
            shlex.split(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
        )
    except OSError as exc:
        log(f"Could not start catalog MCP server: {exc}", "WARNING")
        return []
    try:
        timer_kill = _kill_after(proc, _TIMEOUT)
        _rpc(proc, 1, "initialize", {"protocolVersion": "2025-03-26"})
        result = _rpc(proc, 2, "tools/call", {"name": "list_repos", "arguments": {"limit": 1000}})
        timer_kill.cancel()
        if result.get("isError"):
            raise RuntimeError(result["content"][0]["text"])
        repos = json.loads(result["content"][0]["text"])
        return [r for r in repos if isinstance(r, dict) and r.get("name")]
    except Exception as exc:
        log(f"Catalog MCP lookup failed: {exc}", "WARNING")
        return []
    finally:
        proc.kill()
        proc.wait()


def _kill_after(proc: subprocess.Popen, seconds: int):
    import threading

    timer = threading.Timer(seconds, proc.kill)
    timer.daemon = True
    timer.start()
    return timer


def catalog_history(repos: list[dict]) -> list[str]:
    """Render catalog entries as 'name purpose categories' lines for ideation context."""
    return [
        " ".join(
            str(p) for p in (r["name"], (r.get("purpose") or "")[:80], " ".join(r.get("categories") or []))
            if p
        )
        for r in repos
    ]
