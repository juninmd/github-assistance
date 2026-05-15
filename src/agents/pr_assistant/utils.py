"""Utility functions for PR Assistant Agent."""

_NORMALIZED_CACHE: dict[tuple[str, ...], list[str]] = {}

def _get_normalized(allowed_authors: list[str]) -> list[str]:
    key = tuple(allowed_authors)
    if key not in _NORMALIZED_CACHE:
        _NORMALIZED_CACHE[key] = [a.lower().replace("[bot]", "") for a in allowed_authors]
    return _NORMALIZED_CACHE[key]

def is_trusted_author(author: str, allowed_authors: list[str]) -> bool:
    """Check if the author is in the trusted list."""
    normalized = _get_normalized(allowed_authors)
    return author.lower().replace("[bot]", "") in normalized
