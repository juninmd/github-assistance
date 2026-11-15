"""Credentials pasted into PR comments (text that lives outside git).

No code gate sees a token pasted into a comment or review. Pattern from
``juninmd/base-actions`` (comments-scan). The bot already reads every comment, so
it scans them with the same credential rules as the push guard and posts one
warning per exposed comment. The warning never repeats the value.
"""

from __future__ import annotations

import re
from typing import Any

from src.utils.secret_scan import scan_text

WARNING_MARKER = "<!-- comment-secret-warning:{id} -->"
_ID_RE = re.compile(r"<!-- comment-secret-warning:(\d+) -->")


def find_exposed_comments(comments: list[Any]) -> list[tuple[int, str, list[str]]]:
    """Return ``(comment_id, url, rule_ids)`` for comments that carry a credential."""
    out: list[tuple[int, str, list[str]]] = []
    for c in comments:
        body = getattr(c, "body", "") or ""
        if "comment-secret-warning" in body:  # our own warning
            continue
        rules = sorted({str(h["rule_id"]) for h in scan_text(body)})
        if rules:
            out.append((int(c.id), str(getattr(c, "html_url", "") or ""), rules))
    return out


def already_warned(comments: list[Any]) -> set[int]:
    ids: set[int] = set()
    for c in comments:
        ids.update(int(m) for m in _ID_RE.findall(getattr(c, "body", "") or ""))
    return ids


def build_warning(comment_id: int, url: str, rules: list[str]) -> str:
    where = f"[este comentário]({url})" if url else f"o comentário `{comment_id}`"
    return "\n".join(
        [
            WARNING_MARKER.format(id=comment_id),
            "## 🔑 Possível credencial exposta em comentário\n",
            f"Detectei texto com formato de credencial em {where} (regras: "
            f"{', '.join(f'`{r}`' for r in rules)}). O valor não é repetido aqui.\n",
            "1. **Revogue/rotacione** a credencial agora: apagar o comentário não a protege, "
            "o histórico de edições e notificações por e-mail já a expuseram.",
            "2. Edite ou apague o comentário.",
        ]
    )


def pending_warnings(comments: list[Any]) -> list[str]:
    """Warning bodies for exposed comments that were not warned yet."""
    warned = already_warned(comments)
    return [
        build_warning(cid, url, rules)
        for cid, url, rules in find_exposed_comments(comments)
        if cid not in warned
    ]
