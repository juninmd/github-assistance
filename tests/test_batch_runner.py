"""Tests for the batch runner's dependency-aware scheduling."""

from unittest.mock import patch

from src.agents.batch_runner import _batches, run_all
from src.config.settings import Settings


def test_batches_splits_dependents_into_second_batch():
    batches = _batches(["pr-assistant", "secret-remover", "security-scanner"])
    assert batches == [["pr-assistant", "security-scanner"], ["secret-remover"]]


def test_batches_no_empty_batches_when_only_dependent_agent_enabled():
    """Regression: an empty first batch used to crash ThreadPoolExecutor(max_workers=0)."""
    batches = _batches(["secret-remover"])
    assert batches == [["secret-remover"]]
    assert [] not in batches


def test_batches_empty_agent_list_yields_no_batches():
    assert _batches([]) == []


def test_run_all_with_only_dependent_agent_enabled_does_not_crash():
    """End-to-end regression for the empty-first-batch ValueError. `code-reviewer` is
    always enabled alongside `secret-remover` here (both require AI), so this also
    covers the two-batch happy path."""
    settings = Settings(
        github_token="token",
        enable_product_manager=False,
        enable_interface_developer=False,
        enable_senior_developer=False,
        enable_pr_assistant=False,
        enable_security_scanner=False,
        enable_ci_health=False,
        enable_pr_sla=False,
        enable_jules_tracker=False,
        enable_secret_remover=True,
        enable_project_creator=False,
        enable_branch_cleaner=False,
        enable_intelligence_standardizer=False,
        enable_readme_curator=False,
        enable_ai=True,  # secret-remover is in AGENTS_WITH_AI
    )

    with patch("src.run_agent.run_agent", return_value={"status": "ok"}) as mock_run:
        results = run_all(settings)

    assert results["secret-remover"] == {"status": "ok"}
    assert mock_run.call_count == len(results)


def test_run_all_no_agents_enabled_returns_empty_results():
    settings = Settings(
        github_token="token",
        enable_product_manager=False,
        enable_interface_developer=False,
        enable_senior_developer=False,
        enable_pr_assistant=False,
        enable_security_scanner=False,
        enable_ci_health=False,
        enable_pr_sla=False,
        enable_jules_tracker=False,
        enable_secret_remover=False,
        enable_project_creator=False,
        enable_branch_cleaner=False,
        enable_intelligence_standardizer=False,
        enable_readme_curator=False,
        enable_ai=True,  # unlock code-reviewer (_ALWAYS_ENABLED) too
    )

    with patch("src.run_agent.run_agent", return_value={"status": "ok"}) as mock_run:
        results = run_all(settings)

    # code-reviewer is in _ALWAYS_ENABLED but requires AI; with enable_ai=True it still runs.
    assert "code-reviewer" in results
    mock_run.assert_called_once()


def test_run_all_agent_failure_is_captured_not_raised():
    settings = Settings(
        github_token="token",
        enable_product_manager=False,
        enable_interface_developer=False,
        enable_senior_developer=False,
        enable_pr_assistant=True,
        enable_security_scanner=False,
        enable_ci_health=False,
        enable_pr_sla=False,
        enable_jules_tracker=False,
        enable_secret_remover=False,
        enable_project_creator=False,
        enable_branch_cleaner=False,
        enable_intelligence_standardizer=False,
        enable_readme_curator=False,
    )

    with patch("src.run_agent.run_agent", side_effect=Exception("boom")):
        results = run_all(settings)

    assert results["pr-assistant"] == {"error": "agent execution failed"}
