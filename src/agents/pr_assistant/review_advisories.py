"""Compact, non-blocking review rules: outdated stack/libs and README drift.

One short block shared by every review prompt (opencode JSON, LiteLLM, specialists)
so the wording stays in sync and the token cost is paid once per call.
Findings are advisory (``info``/``nit``): they never block the merge.
"""

from __future__ import annotations

from github.PullRequest import PullRequest

from src.agents.pr_assistant.review_flags import enabled

_README_MAX_CHARS = 1500

STACK_RULE = (
    "Stack: só se o diff tocar stack/dependências, sugira (severity info, não bloqueante) "
    "troca de tecnologia obsoleta/depreciada ou de lib antiga por alternativa moderna, "
    "com o motivo em uma frase (ex.: Node.js→Bun, JavaScript→TypeScript, "
    "moment→date-fns/Temporal, requests→httpx, setup.py→pyproject.toml, "
    "CommonJS→ESM, pacote sem manutenção→fork/substituto ativo). "
    "Sem evidência no diff, não sugira."
)
README_RULE = (
    "README: se a mudança altera uso, comandos, configuração, variáveis de ambiente, "
    "dependências ou comportamento documentado e o README não acompanha (ou ficou "
    "desatualizado), aponte (severity info) o trecho a corrigir e o que escrever."
)
RULES = f"{STACK_RULE}\n{README_RULE}"


def advisories_enabled() -> bool:
    return enabled("REVIEW_ADVISORIES", True)


def rules_block() -> str:
    """Rules text, or '' when disabled via REVIEW_ADVISORIES=false."""
    return RULES if advisories_enabled() else ""


def readme_excerpt(pr: PullRequest) -> str:
    """Head of the base-branch README for diff-only reviews ('' if unavailable)."""
    if not advisories_enabled():
        return ""
    try:
        repo = pr.base.repo
        text = repo.get_readme().decoded_content.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - advisory context only
        return ""
    return text[:_README_MAX_CHARS]


def diff_context(pr: PullRequest) -> str:
    """Rules plus README excerpt, ready to append to a diff-only prompt."""
    rules = rules_block()
    if not rules:
        return ""
    excerpt = readme_excerpt(pr)
    tail = f"\nREADME (início):\n{excerpt}\n" if excerpt else ""
    return f"\n{rules}\n{tail}"
