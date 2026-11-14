"""Blocks a PR whose added lines contain credential-like content.

Runs on every review before any model sees the diff. It scans only lines the PR
adds (``+`` lines of each file patch, not the whole file), so a secret already on
the base branch does not block unrelated work. The verdict is a critical
REQUEST_CHANGES, which the existing review gate turns into draft + failing status
until a new commit removes the credential. Findings never include the secret value.
"""

from __future__ import annotations

from typing import Any

from src.agents.pr_assistant.review_verdict import REQUEST_CHANGES, Finding, ReviewVerdict
from src.utils.secret_scan import scan_text

MODEL_LABEL = "credential-scan"


def added_lines(patch: str) -> str:
    """Keep only lines the patch adds, dropping the ``+++`` file header."""
    kept = [
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return "\n".join(kept)


def pr_added_text(pr: Any) -> str:
    """Added lines across every changed file of the PR, uncapped."""
    parts: list[str] = []
    for f in pr.get_files():
        patch = getattr(f, "patch", None)
        if patch:
            parts.append(added_lines(patch))
    return "\n".join(parts)


def credential_verdict(text: str) -> ReviewVerdict | None:
    """Critical verdict when ``text`` contains credential-like content, else ``None``."""
    findings = scan_text(text, env={})
    if not findings:
        return None
    details = [
        Finding(
            file="(diff)",
            line=int(item["line"]),
            severity="error",
            issue=(
                f"Possível credencial exposta ({item['rule_id']}). Remova o valor do código, "
                "revogue a credencial no provedor e use variável de ambiente ou secret."
            ),
        )
        for item in findings
    ]
    return ReviewVerdict(
        verdict=REQUEST_CHANGES,
        summary="PR bloqueado: possível credencial exposta nas linhas adicionadas.",
        findings=details,
        model=MODEL_LABEL,
    )
