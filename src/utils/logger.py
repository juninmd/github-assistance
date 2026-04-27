"""Structured logger with correlation ID support."""
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    cid = uuid.uuid4().hex[:8]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return _correlation_id.get()


class StructuredLogger:
    """Simple structured logger that emits consistent, parseable lines."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def __init__(self, name: str, min_level: str = "INFO"):
        self.name = name
        self._min = self.LEVELS.get(min_level.upper(), 20)

    def _emit(self, level: str, message: str, **extra: Any) -> None:
        if self.LEVELS.get(level, 0) < self._min:
            return
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        cid = get_correlation_id()
        parts = [f"[{now}]", f"[{level}]", f"[{self.name}]"]
        if cid:
            parts.append(f"[cid:{cid}]")
        parts.append(message)
        if extra:
            kv = " ".join(f"{k}={v!r}" for k, v in extra.items())
            parts.append(f"| {kv}")
        line = " ".join(parts)
        stream = sys.stderr if level in ("ERROR", "CRITICAL") else sys.stdout
        print(line, file=stream)

    def debug(self, msg: str, **kw: Any) -> None:
        self._emit("DEBUG", msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._emit("INFO", msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._emit("WARNING", msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._emit("ERROR", msg, **kw)

    def critical(self, msg: str, **kw: Any) -> None:
        self._emit("CRITICAL", msg, **kw)

    # Compat shim so existing log(msg, level) calls still work
    def __call__(self, message: str, level: str = "INFO") -> None:
        self._emit(level.upper(), message)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)
