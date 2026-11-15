"""In-memory failed-auth throttle for the admin API (brute-force guard)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class AuthThrottle:
    """Blocks a client after `max_failures` bad tokens within `window` seconds."""

    def __init__(self, max_failures: int = 10, window: float = 60.0, clock=time.monotonic) -> None:
        self.max_failures = max_failures
        self.window = window
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, client: str, now: float) -> deque[float]:
        hits = self._failures[client]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            self._failures.pop(client, None)
        return hits

    def retry_after(self, client: str) -> int:
        """Seconds until `client` may retry; 0 when it is not blocked."""
        with self._lock:
            now = self._clock()
            hits = self._prune(client, now)
            if len(hits) < self.max_failures:
                return 0
            return max(1, int(hits[0] + self.window - now) + 1)

    def record_failure(self, client: str) -> None:
        with self._lock:
            self._failures[client].append(self._clock())

    def reset(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)
