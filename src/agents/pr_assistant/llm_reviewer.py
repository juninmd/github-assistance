"""PR code review powered by the LiteLLM proxy (src.ai.litellm_client).

Opt-in, separate from the merge-decision evaluator: reads the PR diff and
asks the configured LiteLLM model for a findings summary, posted once per
PR head SHA. Purely advisory — it never affects merge_policy's decision.
"""

from __future__ import annotations

import os

from github.PullRequest import PullRequest

from src.agents.pr_assistant.pr_diff import build_review_prompt, collect_diff

LLM_REVIEW_MARKER = "<!-- litellm-review -->"


def llm_review_enabled() -> bool:
    return os.getenv("LLM_REVIEW_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def has_existing_llm_review_comment(pr: PullRequest, issue_comments: list | None = None) -> bool:
    try:
        comments = issue_comments if issue_comments is not None else list(pr.get_issue_comments())
        return any(LLM_REVIEW_MARKER in (c.body or "") for c in comments)
    except Exception:
        return False


def review_pr_with_litellm(pr: PullRequest, ai_client) -> tuple[bool, str]:
    """Return (success, report_markdown). report is '' when there is nothing to say."""
    diff = collect_diff(pr)
    if not diff.strip():
        return True, ""
    try:
        report = ai_client.generate(build_review_prompt(pr, diff))
    except Exception as e:  # noqa: BLE001 - advisory feature, never breaks the run
        return False, f"LiteLLM review failed: {e}"
    report = (report or "").strip()
    if not report or report.lower().startswith("no issues found"):
        return True, ""
    return True, report


def build_llm_review_comment(report: str) -> str:
    if not report:
        return ""
    return "\n".join(
        [
            LLM_REVIEW_MARKER,
            "## 🤖 Revisão Automática — LiteLLM\n",
            report,
            "\n---",
            "_Revisão consultiva gerada via LiteLLM por `pr_assistant`; não afeta a decisão de merge._",
        ]
    )
