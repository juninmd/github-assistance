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
from pathlib import Path
from typing import Any

from github.PullRequest import PullRequest

from src.agents.pr_assistant import review_flags, review_git, review_patch
from src.agents.pr_assistant import review_models as models
from src.agents.pr_assistant import review_verdict as rv
from src.agents.pr_assistant import review_workspace as ws
from src.agents.pr_assistant.pr_diff import collect_diff
from src.agents.pr_assistant.review_authors import should_autofix
from src.agents.utils import build_origin_metadata
from src.utils.logger import get_logger

_log = get_logger("review")

_MAX_DIFF_CHARS = 12000
_FALLBACK_ATTEMPTS = 2


def _autofix_enabled() -> bool:
    return review_flags.enabled("REVIEW_AUTOFIX_ENABLED", True) and not review_flags.review_dry_run()


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
        "Use a ferramenta de edição para alterar os arquivos de verdade — não descreva a "
        "correção nem responda em texto.\n"
        "Regras: mudanças mínimas e seguras; não refatore código não relacionado; não altere "
        "testes para mascarar falhas, corrija a causa.\n\n"
        f"Problemas:\n{findings}\n"
    )


def _fallback_verdict(pr: PullRequest, ai_client: Any | None) -> rv.ReviewVerdict | None:
    """Diff-only LiteLLM verdict; retries once because models occasionally emit
    malformed JSON, which would otherwise silently drop the review."""
    if ai_client is None:
        return None
    for attempt in range(_FALLBACK_ATTEMPTS):
        try:
            text = ai_client.generate(_json_prompt(pr, ""))
        except Exception:
            return None
        verdict = rv.parse_review(text, model="cloud/auto (litellm)")
        if verdict is not None:
            return verdict
        _log.warning(
            f"LLM review returned unusable JSON for PR #{pr.number} "
            f"(attempt {attempt + 1}/{_FALLBACK_ATTEMPTS})"
        )
    return None


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


def _fix_is_safe(clone_dir: str, pr: PullRequest, candidates: list[str]) -> rv.ReviewVerdict | None:
    """Review the uncommitted fix; ``None`` unless it is approved with nothing blocking.

    Fail closed: an unusable review of the fix counts as a rejection, so unreviewed
    code never reaches the PR branch.
    """
    diff = ws.local_diff(clone_dir, pr.base.ref, _MAX_DIFF_CHARS, include_worktree=True)
    if not diff.strip():
        return None
    prompt = _json_prompt(pr, diff)
    for model in candidates:
        output = ws.run_opencode(clone_dir, prompt, model, ws.review_timeout())
        fresh = rv.parse_review(output, model=model) if output else None
        if fresh is not None:
            blocking = fresh.blocks(review_flags.gate_min_severity())
            return fresh if fresh.approved and not blocking else None
    return None


def _push_if_verified(
    clone_dir: str, pr: PullRequest, verdict: rv.ReviewVerdict, candidates: list[str], message: str
) -> rv.ReviewVerdict | None:
    """Push the pending fix only after an independent review approves it."""
    checked = _fix_is_safe(clone_dir, pr, candidates)
    if checked is None:
        _log.warning(f"auto-fix for PR #{pr.number} rejected by verification; not pushed")
        review_git.discard_changes(clone_dir)
        return None
    ok, sha = review_git.commit_and_push(clone_dir, pr.head.ref, message)
    if not ok:
        return None
    return replace(
        verdict,
        verdict=rv.APPROVE,
        summary=checked.summary or verdict.summary,
        findings=checked.findings,
        model=checked.model or verdict.model,
        fixed=True,
        commit=sha,
    )


def _apply_fixes(
    clone_dir: str, pr: PullRequest, verdict: rv.ReviewVerdict, candidates: list[str]
) -> rv.ReviewVerdict:
    message = (
        "fix(review): aplica correções da revisão automática\n\n"
        f"{build_origin_metadata('pr_assistant', verdict.model or 'opencode')}"
    )
    fix_models = list(dict.fromkeys([verdict.model or candidates[-1], candidates[-1]]))
    # 1) Deterministic: request a unified diff, apply it, review it, only then push.
    for model in fix_models:
        patch = review_patch.request_patch(clone_dir, verdict, model)
        if patch and review_patch.apply_patch(clone_dir, patch):
            pushed = _push_if_verified(clone_dir, pr, verdict, candidates, message)
            if pushed is not None:
                return pushed
    # 2) Fallback: let opencode edit the files directly (cloud model), same verification.
    ws.run_opencode(clone_dir, _fix_instructions(verdict), candidates[-1], ws.review_timeout())
    pushed = _push_if_verified(clone_dir, pr, verdict, candidates, message)
    return pushed if pushed is not None else verdict


def _via_clone(pr: PullRequest, token: str) -> rv.ReviewVerdict | None:
    candidates = models.candidate_models()
    author = pr.user.login if getattr(pr, "user", None) else ""
    autofix = _autofix_enabled() and should_autofix(author)
    try:
        with tempfile.TemporaryDirectory(prefix=ws.REVIEW_PREFIX) as tmpdir:
            try:
                clone_dir = ws.clone_pr_head(pr, tmpdir, token)
                ws.write_opencode_config(str(Path.home() / ".config" / "opencode"))
                verdict = _review_with_models(clone_dir, pr, candidates)
                if verdict and not verdict.approved and verdict.findings and autofix:
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
