"""Evidence-of-change check: PR descriptions should show the change (screenshots preferred).

Non-blocking by design: a missing section yields a ``warn`` finding that asks the
author to add evidence; it never flips the verdict or touches the merge path.
"""

from __future__ import annotations

import re

from src.agents.pr_assistant import review_flags
from src.agents.pr_assistant.review_verdict import Finding

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)|<img\s[^>]*src=|user-attachments/assets/", re.I)
_SECTION = re.compile(r"^#{1,4}\s*(evid[eê]ncias?|evidence|screenshots?|prints?)\b", re.I | re.M)
_MIN_SECTION_CHARS = 20

EVIDENCE_SECTION = (
    "### Evidências\n"
    "<!-- Anexe prints (antes/depois), saída de testes ou logs que provem a mudança. -->\n"
)
_ASK = (
    "A descrição do PR não traz evidências da mudança. Adicione uma seção `Evidências` "
    "com prints (antes/depois) ou, se não houver UI, a saída dos testes/logs que provam o resultado."
)


def evidence_required() -> bool:
    return review_flags.enabled("REVIEW_REQUIRE_EVIDENCE", True)


def has_evidence(body: str | None) -> bool:
    """True with an image, or an Evidências/Evidence/Screenshots section with real content."""
    text = body if isinstance(body, str) else ""
    if _IMAGE.search(text):
        return True
    match = _SECTION.search(text)
    if not match:
        return False
    rest = re.split(r"^#{1,4}\s", text[match.end():], maxsplit=1, flags=re.M)[0]
    rest = re.sub(r"<!--.*?-->", "", rest, flags=re.S)
    return len(rest.strip()) >= _MIN_SECTION_CHARS


def evidence_finding(body: str | None) -> Finding | None:
    if not evidence_required() or has_evidence(body):
        return None
    return Finding(file="(descrição do PR)", severity="warn", issue=_ASK)
