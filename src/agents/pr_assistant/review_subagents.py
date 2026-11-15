"""Parallel specialist reviewers ("subagents") for the advisory LLM PR review.

One generalist prompt tends to skim. Three narrow reviewers run concurrently on
the same bounded diff, each hunting one defect class; their findings are merged
and de-duplicated. Opt-in (``LLM_REVIEW_SUBAGENTS=true``) because it costs one
LLM call per specialist, and only used when the diff is big enough to deserve
it (``LLM_REVIEW_SUBAGENTS_MIN_CHARS``, default 1500), so trivial PRs stay cheap.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor

from github.PullRequest import PullRequest

from src.agents.pr_assistant.review_advisories import RULES, advisories_enabled, readme_excerpt
from src.agents.pr_assistant.review_flags import enabled

NO_ISSUES = "no issues found"

SPECIALISTS: dict[str, str] = {
    "Segurança": (
        "Focus ONLY on security: injection, secrets/credentials, unsafe deserialization, "
        "path traversal, missing authz/validation, unsafe subprocess use."
    ),
    "Correção": (
        "Focus ONLY on correctness: logic bugs, off-by-one, None/empty handling, wrong "
        "conditions, resource leaks, race conditions, broken error handling, API misuse."
    ),
    "Testes": (
        "Focus ONLY on test gaps: new or changed behaviour in the diff with no test, "
        "removed/weakened assertions, tests that cannot fail."
    ),
}
ADVISORY_SPECIALIST = (
    "Stack e docs",
    "Focus ONLY on outdated stack/libraries and README drift (non-blocking advice). " + RULES,
)


def active_specialists() -> dict[str, str]:
    if not advisories_enabled():
        return dict(SPECIALISTS)
    return {**SPECIALISTS, ADVISORY_SPECIALIST[0]: ADVISORY_SPECIALIST[1]}


def subagents_enabled() -> bool:
    return enabled("LLM_REVIEW_SUBAGENTS", False)


def min_diff_chars() -> int:
    try:
        return int(os.getenv("LLM_REVIEW_SUBAGENTS_MIN_CHARS", "") or 1500)
    except ValueError:
        return 1500


def specialist_prompt(pr: PullRequest, diff: str, focus: str) -> str:
    extra = ""
    if focus.startswith("Focus ONLY on outdated"):
        excerpt = readme_excerpt(pr)
        extra = f"README (head):\n{excerpt}\n\n" if excerpt else ""
    return (
        "You are a senior engineer on a specialist code-review team.\n"
        f"{focus}\n"
        "Review ONLY the diff below. Ignore style nits. Report only concrete, "
        "evidence-backed problems as a short markdown bullet list, each naming the file. "
        f"If there is nothing to flag, reply exactly: No issues found.\n\n"
        f"PR title: {pr.title}\n\n{extra}Diff:\n{diff}"
    )


def _bullets(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("-", "*", "•"))]


def _norm(bullet: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", bullet.lower()).strip()


def merge_findings(results: dict[str, str]) -> str:
    """Merge specialist outputs into one report, dropping empty answers and duplicates."""
    seen: set[str] = set()
    sections: list[str] = []
    for name, text in results.items():
        text = (text or "").strip()
        if not text or text.lower().startswith(NO_ISSUES):
            continue
        items = _bullets(text) or [text]
        fresh = []
        for item in items:
            key = _norm(item)
            if key and key not in seen:
                seen.add(key)
                fresh.append(item)
        if fresh:
            sections.append(f"**{name}**\n" + "\n".join(fresh))
    return "\n\n".join(sections)


def review_with_subagents(pr: PullRequest, diff: str, ai_client) -> tuple[bool, str]:
    """Run all specialists in parallel. ``(ok, merged_report)``; ok if any answered."""

    def run(item: tuple[str, str]) -> tuple[str, str | None]:
        name, focus = item
        try:
            return name, ai_client.generate(specialist_prompt(pr, diff, focus))
        except Exception:  # noqa: BLE001 - one failed specialist must not sink the review
            return name, None

    team = active_specialists()
    with ThreadPoolExecutor(max_workers=len(team)) as pool:
        answers = list(pool.map(run, team.items()))
    results = {name: text for name, text in answers if text is not None}
    if not results:
        return False, "all specialist reviewers failed"
    return True, merge_findings(results)
