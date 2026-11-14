"""LLM usage accounting and response cache shared by every AI client.

Goals: (1) make token spend observable per run, (2) avoid paying twice for
identical prompts (e.g. the same PR diff reviewed again in the same run or,
with ``AI_CACHE_PATH`` set, across runs).

Token counts are estimates (~4 chars/token); providers do not return usage
uniformly, and an estimate is enough to compare before/after.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

CHARS_PER_TOKEN = 4
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("ai_call_depth", default=0)


def estimate_tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN if text else 0


class LLMUsage:
    """Thread-safe counters plus an LRU (optionally sqlite-backed) response cache."""

    def __init__(self, max_entries: int = 256, db_path: str | None = None):
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, str] = OrderedDict()
        self.max_entries = max_entries
        self.db_path = db_path
        self.reset_counters()

    def reset_counters(self) -> None:
        with self._lock:
            self.calls = 0
            self.cache_hits = 0
            self.errors = 0
            self.tokens_in = 0
            self.tokens_out = 0
            self.tokens_saved = 0
            self.seconds = 0.0
            self.by_method: dict[str, int] = {}

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # -- cache -------------------------------------------------------------
    def _db(self) -> sqlite3.Connection | None:
        if not self.db_path:
            return None
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("CREATE TABLE IF NOT EXISTS ai_cache (k TEXT PRIMARY KEY, v TEXT)")
        return conn

    def get(self, key: str) -> str | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        try:
            conn = self._db()
            if conn is None:
                return None
            try:
                row = conn.execute("SELECT v FROM ai_cache WHERE k=?", (key,)).fetchone()
            finally:
                conn.close()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)
        try:
            conn = self._db()
            if conn is not None:
                try:
                    with conn:
                        conn.execute("INSERT OR REPLACE INTO ai_cache VALUES (?,?)", (key, value))
                finally:
                    conn.close()
        except sqlite3.Error:
            pass

    # -- accounting ----------------------------------------------------------
    def record(self, method: str, tin: int, tout: int, seconds: float, *, hit: bool = False,
               error: bool = False) -> None:
        with self._lock:
            self.calls += 0 if hit else 1
            self.by_method[method] = self.by_method.get(method, 0) + 1
            if hit:
                self.cache_hits += 1
                self.tokens_saved += tin + tout
            else:
                self.tokens_in += tin
                self.tokens_out += tout
                self.seconds += seconds
            if error:
                self.errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = self.calls + self.cache_hits
            return {
                "llm_calls": self.calls,
                "llm_cache_hits": self.cache_hits,
                "llm_cache_hit_rate": round(self.cache_hits / total * 100, 1) if total else 0.0,
                "llm_errors": self.errors,
                "llm_tokens_in_est": self.tokens_in,
                "llm_tokens_out_est": self.tokens_out,
                "llm_tokens_saved_est": self.tokens_saved,
                "llm_seconds": round(self.seconds, 2),
                "llm_calls_by_method": dict(self.by_method),
            }

    @staticmethod
    def delta_of(now: dict[str, Any], start: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in now.items():
            if k == "llm_calls_by_method":
                out[k] = {m: n - start.get(k, {}).get(m, 0) for m, n in v.items()
                          if n - start.get(k, {}).get(m, 0)}
            elif k != "llm_cache_hit_rate":
                out[k] = round(v - start.get(k, 0), 2) if isinstance(v, float) else v - start.get(k, 0)
        total = out["llm_calls"] + out["llm_cache_hits"]
        out["llm_cache_hit_rate"] = round(out["llm_cache_hits"] / total * 100, 1) if total else 0.0
        return out

    def delta(self, start: dict[str, Any]) -> dict[str, Any]:
        return self.delta_of(self.snapshot(), start)


def _from_env() -> LLMUsage:
    return LLMUsage(
        max_entries=int(os.getenv("AI_CACHE_MAX_ENTRIES", "256")),
        db_path=os.getenv("AI_CACHE_PATH") or None,
    )


usage = _from_env()
_CACHEABLE = {"generate", "generate_pr_comment"}


def cache_enabled() -> bool:
    return os.getenv("AI_CACHE", "1").lower() not in {"0", "false", "off", "no"}


def instrument(method_name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a client method: count tokens/time, and cache pure text-in/text-out calls."""

    @functools.wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> str:
        depth = _depth.get()
        if depth:  # nested call (e.g. generate_pr_comment -> generate): outermost counts
            return fn(self, *args, **kwargs)
        text_in = "".join(str(a) for a in (*args, *kwargs.values()))
        tin = estimate_tokens(text_in)
        key = None
        if method_name in _CACHEABLE and cache_enabled():
            ident = f"{type(self).__name__}|{getattr(self, 'model', '')}|{method_name}|{text_in}"
            key = hashlib.sha256(ident.encode()).hexdigest()
            hit = usage.get(key)
            if hit is not None:
                usage.record(method_name, tin, estimate_tokens(hit), 0.0, hit=True)
                return hit
        token = _depth.set(depth + 1)
        start = time.monotonic()
        try:
            out = fn(self, *args, **kwargs)
        except Exception:
            usage.record(method_name, tin, 0, time.monotonic() - start, error=True)
            raise
        finally:
            _depth.reset(token)
        usage.record(method_name, tin, estimate_tokens(out or ""), time.monotonic() - start)
        if key and out and out.strip():
            usage.put(key, out)
        return out

    wrapper._ai_instrumented = True  # type: ignore[attr-defined]
    return wrapper
