"""Redis-backed distributed budget guard for the shared GitHub API token.

Every GitHub REST call made through one token reserves budget in a Redis
counter *before* hitting the API, so several agents/pods sharing that token
cannot collectively exceed its hourly quota and trigger HTTP 403. The counter
is reconciled with the ``X-RateLimit-*`` response headers, so Redis tracks
GitHub's own truth instead of a local guess.

Fail-open: when Redis is unreachable the guard disables itself for a short
cooldown instead of blocking or failing the agent run.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

DEFAULT_BUDGET = 4800
DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_MAX_WAIT_SECONDS = 30
_DISABLE_COOLDOWN_SECONDS = 60
_RATE_LIMIT_PATH = "/rate_limit"
_SOCKET_TIMEOUT = 0.5

_REMAINING = "x-ratelimit-remaining"
_LIMIT = "x-ratelimit-limit"
_RESET = "x-ratelimit-reset"


class GitHubRateBudgetExhausted(RuntimeError):
    """The shared GitHub quota for the current window is exhausted."""


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


class GitHubRateLimiter:
    """Distributed token-bucket for one GitHub token, backed by Redis."""

    def __init__(
        self,
        client: Any,
        token: str,
        budget: int = DEFAULT_BUDGET,
        window: int = DEFAULT_WINDOW_SECONDS,
        max_wait: int = DEFAULT_MAX_WAIT_SECONDS,
        namespace: str = "gha:rl",
    ) -> None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        self._client = client
        self._key = f"{namespace}:{digest}"
        self.budget = budget
        self.window = window
        self.max_wait = max_wait
        self._disabled_until = 0.0

    @classmethod
    def from_env(cls, token: str, client: Any | None = None) -> GitHubRateLimiter | None:
        """Build from REDIS_URL/REDIS_HOST env; ``None`` when Redis is unset."""
        if client is None:
            client = _client_from_env()
            if client is None:
                return None
        return cls(
            client=client,
            token=token,
            budget=_int_env("GITHUB_RATE_LIMIT_BUDGET", DEFAULT_BUDGET, 1),
            window=_int_env("GITHUB_RATE_LIMIT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS, 1),
            max_wait=_int_env("GITHUB_RATE_LIMIT_MAX_WAIT_SECONDS", DEFAULT_MAX_WAIT_SECONDS),
        )

    def acquire(self, path: str = "") -> None:
        """Reserve one request. Raise GitHubRateBudgetExhausted when over budget."""
        if _RATE_LIMIT_PATH in path or time.monotonic() < self._disabled_until:
            return
        try:
            used = int(self._client.incrby(self._key, 1))
            if used == 1:
                self._client.expire(self._key, self.window)
            if used <= self.budget:
                return
            ttl = int(self._client.ttl(self._key))
        except Exception:
            self._disable()
            return
        if 0 < ttl <= self.max_wait:
            time.sleep(ttl)
            return
        raise GitHubRateBudgetExhausted(
            f"GitHub rate budget {self.budget}/window exhausted; resets in ~{ttl}s"
        )

    def observe(self, headers: dict[str, Any] | None) -> None:
        """Reconcile the counter with GitHub's reported rate-limit state."""
        if not headers or time.monotonic() < self._disabled_until:
            return
        remaining = headers.get(_REMAINING)
        if remaining is None:
            return
        try:
            limit = int(float(headers.get(_LIMIT, self.budget)))
            used = max(0, limit - int(float(remaining)))
            raw = self._client.get(self._key)
            current = int(raw) if raw is not None else 0
            if used > current:
                self._client.set(self._key, used)
            reset = headers.get(_RESET)
            if reset is not None:
                ttl = max(1, int(float(reset)) - int(time.time()))
                self._client.expire(self._key, ttl)
        except Exception:
            self._disable()

    def _disable(self) -> None:
        self._disabled_until = time.monotonic() + _DISABLE_COOLDOWN_SECONDS


def _client_from_env() -> Any | None:
    """Connect to Redis from env, or return ``None`` when not configured."""
    url = os.getenv("REDIS_URL")
    host = os.getenv("REDIS_HOST")
    if not url and not host:
        return None
    try:
        import redis
    except ImportError:
        return None
    if url:
        return redis.Redis.from_url(
            url, decode_responses=True, socket_timeout=_SOCKET_TIMEOUT,
            socket_connect_timeout=_SOCKET_TIMEOUT,
        )
    return redis.Redis(
        host=host or "localhost",
        port=_int_env("REDIS_PORT", 6379, 1),
        password=os.getenv("REDIS_PASSWORD") or None,
        db=_int_env("REDIS_DB", 0),
        decode_responses=True,
        socket_timeout=_SOCKET_TIMEOUT,
        socket_connect_timeout=_SOCKET_TIMEOUT,
    )
