"""Deterministic auto-fix: ask the model for a unified diff and apply it.

Editing files through the agent tool is model-dependent and was unreliable, so
the primary fix path requests a ``git``-style patch and applies it with
``git apply``; a clean apply is proof the fix exists.
"""

from __future__ import annotations

import re

from src.agents.pr_assistant import review_git
from src.agents.pr_assistant import review_workspace as ws
from src.agents.pr_assistant.review_verdict import ReviewVerdict

_PATCH_FENCE = re.compile(r"```(?:diff|patch)?\n(.*?)```", re.DOTALL)


def fix_prompt(verdict: ReviewVerdict) -> str:
    findings = "\n".join(
        f"- `{f.file}` (linha {f.line or '?'}, {f.severity}): {f.issue}" for f in verdict.findings
    )
    return (
        "Você é um engenheiro sênior. Gere um patch unificado no formato `git diff` que "
        "corrija APENAS os problemas abaixo no repositório deste PR.\n"
        "Regras: mudanças mínimas e seguras; não refatore código não relacionado; não altere "
        "testes para mascarar falhas, corrija a causa.\n"
        "Responda SOMENTE com o patch, começando por `diff --git` e sem cercas markdown.\n\n"
        f"Problemas:\n{findings}\n"
    )


def extract_patch(text: str | None) -> str:
    """Return the first git-style unified diff found in a model answer."""
    if not text:
        return ""
    fence = _PATCH_FENCE.search(text)
    body = fence.group(1) if fence else text
    for marker in ("diff --git", "--- "):
        index = body.find(marker)
        if index != -1:
            return body[index:].strip() + "\n"
    return ""


def request_patch(clone_dir: str, verdict: ReviewVerdict, model: str) -> str:
    output = ws.run_opencode(clone_dir, fix_prompt(verdict), model, ws.review_timeout())
    return extract_patch(output) if output else ""


def apply_patch(clone_dir: str, patch: str) -> bool:
    return review_git.apply_patch(clone_dir, patch)
