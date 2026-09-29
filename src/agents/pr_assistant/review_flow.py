"""Advisory PR code review: free opencode first, cluster cloud/auto fallback.

The review clones the PR head, tries free opencode models (then ``cloud/auto``)
to obtain a JSON verdict, and — when it reports blocking findings — asks the
model to apply the fixes in the same clone and pushes them back to the PR branch.
Every failure degrades to a diff-only LiteLLM call or to no review; it never
raises into the PR Assistant run and never touches the merge path.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import replace
from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant import review_git
from src.agents.pr_assistant import review_models as models
from src.agents.pr_assistant import review_verdict as rv
from src.agents.pr_assistant import review_workspace as ws
from src.agents.pr_assistant.pr_diff import collect_diff
from src.agents.utils import build_origin_metadata

_MAX_DIFF_CHARS = 12000


def _autofix_enabled() -> bool:
    return os.getenv("REVIEW_AUTOFIX_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def _instructions(pr: PullRequest) -> str:
    return (
        "Você é um engenheiro sênior revisando um pull request. Leia o repositório no "
        "diretório atual e aplique a skill `code-review` (e `security-ops`/`test-engineering` "
        "quando fizer sentido). Aponte apenas defeitos reais: bugs, falhas de segurança e "
        "regressões de comportamento; ignore detalhes de estilo.\n\n"
        "Responda com APENAS um objeto JSON, em português, sem texto fora do JSON:\n"
        '{"verdict":"APPROVE|REQUEST_CHANGES","summary":"resumo curto",'
        '"findings":[{"file":"caminho","line":0,"severity":"error|warn|nit","issue":"..."}]}\n'
        "Use APPROVE quando não houver problema bloqueante.\n\n"
        f"Título do PR: {pr.title}\n"
    )


def _json_prompt(pr: PullRequest, diff: str) -> str:
    body = diff or collect_diff(pr)
    return f"{_instructions(pr)}\nDiff:\n{body}"


def _fix_instructions(verdict: rv.ReviewVerdict) -> str:
    findings = "\n".join(
        f"- `{f.file}` (linha {f.line or '?'}, {f.severity}): {f.issue}" for f in verdict.findings
    )
    return (
        "Você é um engenheiro sênior. Corrija APENAS os problemas listados abaixo no "
        "repositório deste PR.\n"
        "Regras: mudanças mínimas e seguras; não refatore código não relacionado; não altere "
        "testes para mascarar falhas, corrija a causa. Ao terminar, não escreva nenhum texto.\n\n"
        f"Problemas:\n{findings}\n"
    )


def _fallback_verdict(pr: PullRequest, ai_client: Any | None) -> rv.ReviewVerdict | None:
    if ai_client is None:
        return None
    try:
        text = ai_client.generate(_json_prompt(pr, ""))
    except Exception:
        return None
    return rv.parse_review(text, model="cloud/auto (litellm)")


def _review_with_models(
    clone_dir: str, pr: PullRequest, candidates: list[str]
) -> rv.ReviewVerdict | None:
    prompt = _json_prompt(pr, ws.local_diff(clone_dir, pr.base.ref, _MAX_DIFF_CHARS))
    for model in candidates:
        output = ws.run_opencode(clone_dir, prompt, model, ws.review_timeout())
        verdict = rv.parse_review(output, model=model) if output else None
        if verdict is not None:
            return verdict
    return None


def _apply_fixes(
    clone_dir: str, pr: PullRequest, verdict: rv.ReviewVerdict, candidates: list[str]
) -> rv.ReviewVerdict:
    ws.run_opencode(
        clone_dir, _fix_instructions(verdict), verdict.model or candidates[-1], ws.review_timeout()
    )
    message = (
        "fix(review): aplica correções da revisão automática\n\n"
        f"{build_origin_metadata('pr_assistant', verdict.model or 'opencode')}"
    )
    ok, sha = review_git.commit_and_push(clone_dir, pr.head.ref, message)
    if not ok:
        return verdict
    fixed = replace(verdict, fixed=True, commit=sha)
    fresh = _review_with_models(clone_dir, pr, candidates)
    if fresh is not None and fresh.approved:
        return replace(
            fixed,
            verdict=rv.APPROVE,
            summary=fresh.summary,
            findings=fresh.findings,
            model=fresh.model or fixed.model,
        )
    return fixed


def _via_clone(pr: PullRequest, token: str) -> rv.ReviewVerdict | None:
    candidates = models.candidate_models()
    try:
        with tempfile.TemporaryDirectory(prefix=ws.REVIEW_PREFIX) as tmpdir:
            try:
                clone_dir = ws.clone_pr_head(pr, tmpdir, token)
                ws.write_opencode_config(clone_dir)
                verdict = _review_with_models(clone_dir, pr, candidates)
                if verdict and not verdict.approved and verdict.findings and _autofix_enabled():
                    verdict = _apply_fixes(clone_dir, pr, verdict, candidates)
                return verdict
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        return None


def run_review(pr: PullRequest, ai_client: Any | None = None) -> rv.ReviewVerdict | None:
    """Return a review verdict, or ``None`` when the review could not run."""
    ws.cleanup_stale_review_dirs()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT", "")
    verdict = _via_clone(pr, token) if token else None
    return verdict or _fallback_verdict(pr, ai_client)
