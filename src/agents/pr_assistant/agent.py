"""
PR Assistant Agent - Auto-merges PRs and manages pipelines.

The behaviour lives in cohesive mixins (Antigravity 150-line guideline):

- ``run_flow``        — run loop, PR discovery and per-PR orchestration
- ``skip_mixin``      — which PRs to skip, no-CI tagging, bot suggestions
- ``pipeline_flow``   — pipeline fix/warn/skip decisions
- ``merge_flow``      — comment evaluation and the SHA-locked merge
- ``notify_mixin``    — best-effort comments/notifications
- ``review_mixin``    — advisory LiteLLM/opencode reviews

This module only wires them together and owns the shared state.
"""

import os
import threading

from src.agents.base_agent import BaseAgent
from src.agents.pr_assistant.llm_reviewer import llm_review_enabled
from src.agents.pr_assistant.merge_flow import MergeFlowMixin
from src.agents.pr_assistant.merge_policy import MergePolicy
from src.agents.pr_assistant.notify_mixin import NotifyMixin
from src.agents.pr_assistant.opencode_reviewer import opencode_review_enabled
from src.agents.pr_assistant.pipeline_flow import PipelineFlowMixin
from src.agents.pr_assistant.review_mixin import ReviewMixin
from src.agents.pr_assistant.run_flow import RunFlowMixin
from src.agents.pr_assistant.skip_mixin import SkipMixin
from src.ai import get_ai_client
from src.config.autonomy_policy import AutonomyPolicy
from src.config.settings import DEFAULT_OLLAMA_MODEL


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    """Read an integer env var, returning a bounded default when missing/invalid."""
    try:
        return max(minimum, int(os.getenv(name, "") or default))
    except ValueError:
        return default


class PRAssistantAgent(
    ReviewMixin,
    MergeFlowMixin,
    PipelineFlowMixin,
    SkipMixin,
    NotifyMixin,
    RunFlowMixin,
    BaseAgent,
):
    """Monitors and processes PRs across all repositories."""

    def __init__(
        self,
        *args,
        ai_provider: str = "ollama",
        ai_model: str = DEFAULT_OLLAMA_MODEL,
        target_owner: str = "juninmd",
        min_pr_age_minutes: int = 10,
        pr_ref: str | None = None,
        bypass_validations: bool = False,
        comment_ai_enabled: bool = True,
        simulation_mode: bool = False,
        autonomy_policy_path: str | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="pr_assistant", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = target_owner
        self.min_pr_age_minutes = min_pr_age_minutes
        self.pr_ref = pr_ref
        # Autonomous merge never bypasses pipeline checks: validation is mandatory.
        self.bypass_validations = False
        self.comment_ai_enabled = comment_ai_enabled
        self.simulation_mode = simulation_mode
        self.autonomy = AutonomyPolicy(
            autonomy_policy_path or os.getenv("AUTONOMY_POLICY_PATH", "config/autonomy.json")
        )
        self.merge_policy = MergePolicy()
        self.ai_client = None
        if self.comment_ai_enabled:
            self.ai_client = get_ai_client(
                ai_provider, model=ai_model, **(kwargs.get("ai_config") or {})
            )
        # Advisory PR diff review via the LiteLLM proxy; independent of the
        # merge-decision ai_client above and opt-in (LLM_REVIEW_ENABLED).
        self.llm_reviewer_client = None
        if llm_review_enabled():
            self.llm_reviewer_client = get_ai_client(
                "litellm", model=os.getenv("LLM_REVIEW_MODEL", "cloud/auto")
            )
        # Advisory PR review via opencode with the `code-review` skills and the
        # cluster LiteLLM model; opt-in (OPENCODE_REVIEW_ENABLED). The LiteLLM
        # client is only a diff-only fallback when opencode cannot run.
        self.opencode_review_active = opencode_review_enabled()
        self.review_ai_client = None
        if self.opencode_review_active:
            self.review_ai_client = get_ai_client(
                "litellm", model=os.getenv("LLM_REVIEW_MODEL", "cloud/auto")
            )
        # One opencode (Node) process at a time: 5 in parallel OOMKilled the pod at 2Gi.
        self._opencode_review_slot = threading.Semaphore(1)
        # Serialized reviews are slow, so bound how many start per run and how long a
        # worker waits for the slot; every skip is logged so the run is observable.
        self._review_budget = _env_int("OPENCODE_REVIEW_MAX_PER_RUN", 4, 0)
        self._review_wait = _env_int("OPENCODE_REVIEW_WAIT_SECONDS", 120, 0)
        self._reviews_started = 0
        self._review_lock = threading.Lock()

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def uses_repository_allowlist(self) -> bool:
        return False
