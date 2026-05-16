"""
GitHub API response caching layer.
Provides LRU caching for expensive API calls to reduce rate limit consumption.
"""
import threading
from collections import OrderedDict
from typing import Any


class GitHubAPICache:
    """Thread-safe LRU cache for GitHub API responses."""

    _instance: "GitHubAPICache | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "GitHubAPICache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_size: int = 500, ttl_seconds: int = 300):
        if self._initialized:
            return
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._initialized = True

    def get(self, key: str) -> Any | None:
        import time
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.monotonic() - timestamp < self._ttl:
                    self._cache.move_to_end(key)
                    return value
                else:
                    del self._cache[key]
            return None

    def set(self, key: str, value: Any) -> None:
        import time
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.monotonic())
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


def get_cache() -> GitHubAPICache:
    """Get the singleton cache instance."""
    return GitHubAPICache()
