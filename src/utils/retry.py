"""Retry decorator with exponential backoff and jitter."""
import functools
import random
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    import requests
    if isinstance(exc, requests.HTTPError):
        status = getattr(exc.response, "status_code", None)
        return status in _RETRYABLE_STATUS
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    return False


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable: Callable[[Exception], bool] = _is_retryable,
    logger: Callable[[str], None] | None = None,
) -> Callable[[F], F]:
    """Decorator: retry with exponential backoff + jitter on retryable errors."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts or not retryable(exc):
                        raise
                    jitter = random.uniform(0, delay * 0.3)
                    wait = min(delay + jitter, max_delay)
                    if logger:
                        logger(
                            f"[retry] {func.__name__} attempt {attempt}/{max_attempts} "
                            f"failed: {exc!r}. Retrying in {wait:.1f}s..."
                        )
                    time.sleep(wait)
                    delay = min(delay * backoff_factor, max_delay)
            return None  # unreachable

        return wrapper  # type: ignore[return-value]

    return decorator
