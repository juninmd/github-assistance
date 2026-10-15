"""Shared interface for the PR Assistant mixins.

Declares the attributes and cross-mixin methods so each mixin type-checks in
isolation (pyright basic). Concrete implementations live in the mixin modules;
``PRAssistantAgent`` composes them and every stub below is overridden.
"""

from __future__ import annotations

from typing import Any


class PRAssistantBase:
    """Attributes and methods shared by the PR Assistant mixins."""

    # Shared state, set by BaseAgent / PRAssistantAgent.__init__.
    github_client: Any
    telegram: Any
    log: Any
    autonomy: Any
    merge_policy: Any
    ai_client: Any
    target_owner: str
    pr_ref: str | None
    simulation_mode: bool
    min_pr_age_minutes: int
    llm_reviewer_client: Any
    review_ai_client: Any
    opencode_review_active: bool
    _opencode_review_slot: Any
    _review_lock: Any
    _review_budget: int
    _review_wait: int
    _reviews_started: int

    # run_flow
    def run(self) -> dict[str, Any]: ...

    def _process_pr(self, pr, results: dict) -> None: ...

    # skip_mixin
    def _skip_young_pr(self, pr, results: dict, repo_name: str) -> bool: ...

    def _skip_labeled_pr(self, pr, results: dict, repo_name: str) -> bool: ...

    def _skip_untrusted_pr(self, pr, results: dict, repo_name: str) -> bool: ...

    def _record_skip(
        self, results: dict, pr_number: int, title: str, repo_name: str, reason: str
    ) -> None: ...

    def _tag_no_ci(self, pr) -> None: ...

    def _is_trusted_author(self, login: str) -> bool: ...

    def _try_accept_suggestions(self, pr) -> None: ...

    # pipeline_flow
    def _handle_pipeline_and_skip(
        self, pr, results: dict, issue_comments: list | None = None, status: dict | None = None
    ) -> bool: ...

    def _warn_pipeline_failure(
        self, pr, status: dict, results: dict, issue_comments: list | None = None
    ) -> None: ...

    # merge_flow
    def _resolve_mergeable(self, pr, repo_name: str) -> Any | None: ...

    def _try_merge(self, pr, results: dict, issue_comments: list | None = None) -> None: ...

    def _record_blocked(
        self, results: dict, pr, repo_name: str, reason: str, sha: str | None = None
    ) -> None: ...

    def _evaluate_comments_with_llm(
        self, pr, issue_comments: list | None = None
    ) -> tuple[bool, str]: ...

    # notify_mixin
    def _handle_conflicts(self, pr, results: dict, issue_comments: list | None = None) -> None: ...

    def _notify_conflicts(self, pr, issue_comments: list | None = None) -> None: ...

    def _notify_merged(self, pr, issue_comments: list | None = None) -> None: ...

    def _notify_merge_failed(self, pr, error: str, issue_comments: list | None = None) -> None: ...

    def _notify_pipeline_pending(
        self, pr, state: str, issue_comments: list | None = None
    ) -> None: ...

    def _notify_conflict_resolved(self, pr, msg: str) -> None: ...

    # review_mixin
    def _run_llm_review(self, pr, issue_comments: list | None = None) -> None: ...

    def _run_opencode_review(self, pr, issue_comments: list | None = None) -> None: ...

    def _acquire_review_slot(self, pr) -> bool: ...

    def _review_gate_enabled(self, pr) -> bool: ...

    def _apply_review_gate(self, pr, verdict, jules: bool) -> None: ...

    def _apply_review_label(self, pr, label: str) -> None: ...
