"""Utility functions for PR Assistant Agent."""

from github.IssueComment import IssueComment

_NORMALIZED_CACHE: dict[tuple[str, ...], list[str]] = {}

def _get_normalized(allowed_authors: list[str]) -> list[str]:
    key = tuple(allowed_authors)
    if key not in _NORMALIZED_CACHE:
        _NORMALIZED_CACHE[key] = [a.lower().replace("[bot]", "") for a in allowed_authors]
    return _NORMALIZED_CACHE[key]

def is_trusted_author(author: str, allowed_authors: list[str]) -> bool:
    normalized = _get_normalized(allowed_authors)
    return author.lower().replace("[bot]", "") in normalized

def is_human_comment(comment: IssueComment, allowed_authors: list[str]) -> bool:
    if not comment.user:
        return False
    if is_trusted_author(comment.user.login, allowed_authors):
        return False
    if comment.body and "You have reached your Codex usage limits" in comment.body:
        return False
    return True
