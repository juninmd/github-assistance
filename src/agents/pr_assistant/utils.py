"""Utility functions for PR Assistant Agent."""

def is_trusted_author(author: str, allowed_authors: list[str]) -> bool:
    """Check if the author is in the trusted list."""
    normalized = [a.lower().replace("[bot]", "") for a in allowed_authors]
    return author.lower().replace("[bot]", "") in normalized
