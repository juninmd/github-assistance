"""Owner portfolio profile: what the owner builds by hand vs. what earlier runs auto-generated."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

AUTONOMOUS_MARKER = "criado de forma autônoma"
MAX_EXEMPLARS = 25
MAX_GENERATED = 15
MAX_LANGUAGES = 4
MIN_DESCRIPTION = 15
_NON_STACK = {"dockerfile", "makefile", "shell", "html", "css", "powershell", "batchfile"}


@dataclass(frozen=True)
class Portfolio:
    exemplars: list[str] = field(default_factory=list)  # hand-built repos, "name (Lang): description"
    generated: list[str] = field(default_factory=list)  # names of earlier auto-generated repos
    languages: list[str] = field(default_factory=list)  # most used first


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_portfolio(repos: list[Any], owner: str = "") -> Portfolio:
    """Split the owner's repos into hand-built exemplars and auto-generated ones (the anti-pattern)."""
    exemplars: list[str] = []
    generated: list[str] = []
    languages: Counter[str] = Counter()
    for repo in repos:
        name = _text(getattr(repo, "name", None))
        if not name or getattr(repo, "archived", False) is True or getattr(repo, "fork", False) is True:
            continue
        login = _text(getattr(getattr(repo, "owner", None), "login", None))
        if owner and login and login.lower() != owner.lower():
            continue  # collaborator/org repos do not define the owner's taste
        description = " ".join(_text(getattr(repo, "description", None)).split())
        if AUTONOMOUS_MARKER in description.lower():
            generated.append(name)
            continue
        language = _text(getattr(repo, "language", None))
        if language and language.lower() not in _NON_STACK:
            languages[language] += 1
        if len(description) >= MIN_DESCRIPTION and len(exemplars) < MAX_EXEMPLARS:
            exemplars.append(f"{name} ({language or 'n/a'}): {description[:120]}")
    return Portfolio(
        exemplars=exemplars,
        generated=generated[:MAX_GENERATED],
        languages=[lang for lang, _ in languages.most_common(MAX_LANGUAGES)],
    )
