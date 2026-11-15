"""Optional tokenix integration for opencode runs (token savings).

tokenix (https://github.com/juninmd/tokenix) is a local code index exposed to
opencode as an MCP server: the agent asks for symbols/callers/impact instead of
reading whole files. Everything here is fail-open: when the binary is missing,
the toggle is off, or indexing fails, the run proceeds exactly as before.

opencode 2.x talks to a long-lived background service that keeps the environment
it was started with, so the MCP entry is injected once per process through
``OPENCODE_CONFIG_CONTENT`` (:func:`configure_environ`, called at settings load)
instead of per run. Per run, :func:`session` only builds the clone's index and
removes it afterwards. The index lives under ``~/.tokenix`` (never in the clone),
so nothing is staged or committed.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache

DEFAULT_INDEX_TIMEOUT = 120
STALE_SECONDS = 7200
TOOL_PREFIX = "tokenix_"
CONFIG_ENV = "OPENCODE_CONFIG_CONTENT"


def enabled() -> bool:
    """Toggle: ``TOKENIX_ENABLED`` (env > config/features.toml), default on."""
    return os.getenv("TOKENIX_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def binary() -> str | None:
    return shutil.which(os.getenv("TOKENIX_BIN", "").strip() or "tokenix")


def _index_timeout() -> int:
    try:
        return max(5, int(os.getenv("TOKENIX_INDEX_TIMEOUT_SECONDS", "") or DEFAULT_INDEX_TIMEOUT))
    except ValueError:
        return DEFAULT_INDEX_TIMEOUT


def _home() -> str:
    return os.getenv("TOKENIX_HOME") or os.path.join(os.path.expanduser("~"), ".tokenix")


@lru_cache(maxsize=4)
def version(cmd: str) -> str:
    """``1.1.1`` for ``tokenix 1.1.1``; empty when it cannot be read."""
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [cmd, "--version"], capture_output=True, text=True, timeout=15,
        ).stdout.split()
    except (subprocess.SubprocessError, OSError):
        return ""
    return out[-1] if out else ""


def configure_environ() -> bool:
    """Register the tokenix MCP server for opencode via env; True when active.

    Merges into an existing ``OPENCODE_CONFIG_CONTENT``; an unparsable one is
    left untouched (tokenix stays off rather than clobbering the deployment's config).
    """
    cmd = binary() if enabled() else None
    if not cmd:
        return False
    try:
        config = json.loads(os.environ.get(CONFIG_ENV) or "{}")
        mcp = config.setdefault("mcp", {})
        if not isinstance(mcp, dict):
            return False
    except (ValueError, AttributeError):
        return False
    mcp.setdefault("tokenix", {"type": "local", "command": [cmd, "mcp"], "enabled": True})
    os.environ[CONFIG_ENV] = json.dumps(config, separators=(",", ":"))
    return True


def is_active() -> bool:
    """tokenix is enabled, installed and registered for opencode in this process."""
    try:
        return bool(binary()) and enabled() and "tokenix" in json.loads(os.environ.get(CONFIG_ENV) or "{}").get("mcp", {})
    except (ValueError, AttributeError):
        return False


def harness_suffix(active: bool) -> str:
    """`` + tokenix 1.1.1`` for the harness label, empty when tokenix was not active."""
    cmd = binary()
    return f" + tokenix {version(cmd)}".rstrip() if active and cmd else ""


def calls(tools: tuple[str, ...]) -> int:
    """How many tokenix MCP tools the run actually called."""
    return sum(1 for tool in tools if tool.startswith(TOOL_PREFIX))


def _project_files(clone_dir: str) -> list[str]:
    ident = hashlib.sha256(os.path.realpath(clone_dir).encode()).hexdigest()[:16]
    return glob.glob(os.path.join(_home(), f"{ident}.*"))


def sweep_stale(now: float | None = None) -> None:
    """Drop index files left by a killed run (older than two hours)."""
    cutoff = (now or time.time()) - STALE_SECONDS
    for path in glob.glob(os.path.join(_home(), "[0-9a-f]" * 16 + ".*")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            continue


@contextmanager
def session(clone_dir: str, log: Callable[..., None] | None = None) -> Iterator[bool]:
    """Build the clone's tokenix index; yield True when tokenix is usable for the run."""
    say = log or (lambda *_a, **_k: None)
    cmd = binary()
    if not (cmd and is_active()):
        yield False
        return
    try:
        sweep_stale()
        try:
            res = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [cmd, "index", "."], cwd=clone_dir, capture_output=True, text=True,
                timeout=_index_timeout(),
            )
            ready = res.returncode == 0
            if not ready:
                say(f"tokenix off for this run (index rc={res.returncode})", "WARNING")
        except (subprocess.SubprocessError, OSError) as exc:
            ready = False
            say(f"tokenix off for this run (index failed: {exc})", "WARNING")
        yield ready
    finally:
        for path in _project_files(clone_dir):
            try:
                os.remove(path)
            except OSError:
                pass
