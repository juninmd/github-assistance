"""Merge handling for repos whose GitHub Actions cannot start (billing/spending limit).

When the pipeline never ran because of billing, CI says nothing about the code.
The bot still merges (billing must not block), but only after its own checks —
credentials in the added lines — find nothing, and it leaves a disclaimer on the
PR saying CI was not executed and why. Pattern taken from
``juninmd/base-actions`` (``auto_merge_billing_blocked.py``).
"""

from __future__ import annotations

import re
from itertools import islice
from typing import Any

from src.utils.secret_scan import scan_text

BILLING_DISCLAIMER_MARKER = "<!-- billing-blocked-disclaimer -->"
_MAX_FILES = 100

# Same rule as base-actions validate-pr: secret-bearing files must not be tracked
# (outside test/fixture folders). Without CI that check never runs, so do it here.
_FORBIDDEN_FILE = re.compile(
    r"(^|/)\.env$|(^|/)\.env\.(local|production|prod|staging|dev)$|(^|/)id_rsa$|(^|/).+\.pem$|(^|/).+\.key$"
)
_TEST_DIR = re.compile(r"(^|/)(tests?|fixtures?|spec|examples?|mocks?)/")


def is_forbidden_file(path: str) -> bool:
    return bool(_FORBIDDEN_FILE.search(path)) and not _TEST_DIR.search(path)


def is_billing_blocked(status: dict[str, Any]) -> bool:
    """True when at least one check was refused for billing reasons."""
    return bool(status.get("billing_checks"))


def scan_added_lines(pr: Any) -> list[dict[str, str | int]]:
    """Credential scan over the lines a PR adds (no clone needed). Never returns values."""
    findings: list[dict[str, str | int]] = []
    for f in islice(pr.get_files(), _MAX_FILES):
        if getattr(f, "status", "") != "removed" and is_forbidden_file(f.filename):
            findings.append({"file": f.filename, "rule_id": "forbidden-secret-file", "line": 0})
        patch = getattr(f, "patch", None) or ""
        added = "\n".join(
            line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
        )
        for hit in scan_text(added):
            findings.append({"file": f.filename, "rule_id": hit["rule_id"], "line": hit["line"]})
    return findings


def build_disclaimer(billing_checks: list[str], sha: str) -> str:
    names = ", ".join(f"`{c}`" for c in billing_checks[:10]) or "—"
    return "\n".join(
        [
            BILLING_DISCLAIMER_MARKER,
            "## ⚠️ Pipeline não executada (billing do GitHub Actions)\n",
            f"Os checks {names} **não rodaram** no commit `{sha[:7]}`: o GitHub Actions "
            "recusou iniciar os jobs por limite de gasto/pagamento da conta (comum em "
            "repositórios privados). Isso **não é uma falha do código**.\n",
            "Este PR foi mesclado pelo bot **sem CI**, com base apenas em: sem conflitos, "
            "sem credenciais nas linhas adicionadas e aprovação da análise automática.",
            "Recomenda-se rodar a pipeline/testes localmente ou após regularizar o billing.",
        ]
    )


def has_disclaimer(comments: list) -> bool:
    return any(BILLING_DISCLAIMER_MARKER in (getattr(c, "body", "") or "") for c in comments)
