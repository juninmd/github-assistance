"""Rubric-based README quality scoring.

Pure and dependency-free: turns a README's text into a 0-100 score plus the
list of missing elements, so the curator acts only on READMEs that are actually
below the bar and can tell the model exactly what to add.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_MIN_SCORE = 80

_BADGE = re.compile(r"(shields\.io|badge\.svg|img\.shields|badgen\.net)", re.IGNORECASE)
_IMAGE = re.compile(r"(!\[[^\]]*\]\(|```mermaid|<img\s)", re.IGNORECASE)
_HEADER = re.compile(r"^#{2,3}\s+\S", re.MULTILINE)

_INSTALL = ("install", "instala", "setup", "getting started", "começando", "pré-requisit", "prerequisit")
_USAGE = ("usage", "uso", "quickstart", "como usar", "example", "exemplo", "run", "execut")
_CONFIG = ("config", "environment variable", "variável de ambiente", "variáveis de ambiente", ".env", "options")
_LICENSE = ("license", "licença", "licencia")
_CONTRIB = ("contributing", "contribui", "development", "desenvolvimento")


def _first_paragraph(body: str) -> str:
    """The prose right after the title, skipping badges/images and headers."""
    paragraph: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith(("#", "![", "[![", "<img", "|", ">", "-", "*")):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


@dataclass(frozen=True)
class ReadmeScore:
    """A README score (0-100) with the criteria that were not met."""

    score: int
    missing: list[str] = field(default_factory=list)

    def needs_work(self, min_score: int) -> bool:
        return self.score < min_score


def _has(content: str, needles: tuple[str, ...]) -> bool:
    low = content.lower()
    return any(n in low for n in needles)


def score_readme(content: str | None) -> ReadmeScore:
    """Score a README against a professional-quality rubric."""
    text = content or ""
    if not text.strip():
        return ReadmeScore(0, ["title", "description", "installation", "usage"])

    score = 0
    missing: list[str] = []

    def check(label: str, points: int, ok: bool) -> None:
        nonlocal score
        if ok:
            score += points
        else:
            missing.append(label)

    stripped = text.lstrip()
    check("title", 5, stripped.startswith("# "))
    body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    check("description", 10, len(_first_paragraph(body)) >= 120)
    check("sections", 15, len(_HEADER.findall(text)) >= 4)
    check("installation", 15, _has(text, _INSTALL))
    check("usage", 15, _has(text, _USAGE))
    check("configuration", 10, _has(text, _CONFIG))
    check("badges", 10, bool(_BADGE.search(text)))
    check("license", 5, _has(text, _LICENSE))
    check("contributing", 5, _has(text, _CONTRIB))
    check("visual (diagram/screenshot)", 10, bool(_IMAGE.search(text)))

    return ReadmeScore(min(score, 100), missing)
