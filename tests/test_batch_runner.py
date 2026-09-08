"""Batch runner: dependency-aware scheduling, dependents only after real success."""

from unittest.mock import patch

import pytest

from src.agents.batch_runner import _batches, run_all
from src.config.settings import Settings


def test_batches_splits_dependents_into_second_batch():
    batches = _batches(["pr-assistant", "secret-remover", "security-scanner"])
    assert batches == [["pr-assistant", "security-scanner"], ["secret-remover"]]


def test_batches_no_empty_batches_when_only_dependent_agent_enabled():
    batches = _batches(["secret-remover"])
    assert batches == [["secret-remover"]]
    assert [] not in batches


def test_batches_empty_agent_list_yields_no_batches():
    assert _batches([]) == []


def test_batches_rejects_circular_dependencies():
    from src.agents.orchestration import AgentOrchestrator, AgentPriority

    orch = AgentOrchestrator()
    orch.register_agent("a", AgentPriority.MEDIUM, depends_on=["b"])
    orch.register_agent("b", AgentPriority.MEDIUM, depends_on=["a"])
    with pytest.raises(ValueError, match="circular"):
        orch.get_parallel_batches(["a", "b"])


def _settings(**overrides) -> Settings:
    from typing import Any

    base: dict[str, Any] = dict(
        github_token="token",
        enable_product_manager=False,
        enable_interface_developer=False,
        enable_senior_developer=False,
        enable_pr_assistant=False,
        enable_security_scanner=True,
        enable_ci_health=False,
        enable_pr_sla=False,
        enable_jules_tracker=False,
        enable_secret_remover=True,
        enable_project_creator=False,
        enable_branch_cleaner=False,
        enable_intelligence_standardizer=False,
        enable_readme_curator=False,
        enable_ai=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_run_all_only_dependent_enabled_does_not_crash():
    settings = _settings()
    with patch("src.run_agent.run_agent", return_value={"status": "ok"}) as mock_run:
        results = run_all(settings)
    assert results["secret-remover"] == {"status": "ok"}
    assert mock_run.call_count == len(results)


def test_dependent_blocked_when_dependency_fails():
    """secret-remover must NOT run when security-scanner fails."""
    results = {"security-scanner": {"error": "scan failed"}}

    def fake_run(name, *args, **kwargs):
        return results.get(name, {"status": "ok"})

    settings = _settings()
    with patch("src.run_agent.run_agent", side_effect=fake_run):
        out = run_all(settings)
    assert out["secret-remover"]["status"] == "blocked"
    assert "security-scanner" in out["secret-remover"]["error"]


def test_dependent_runs_when_dependency_succeeds():
    def fake_run(name, *args, **kwargs):
        return {"status": "ok"}

    settings = _settings()
    with patch("src.run_agent.run_agent", side_effect=fake_run) as mock_run:
        out = run_all(settings)
    assert out["secret-remover"]["status"] == "ok"
    names = [call.args[0] for call in mock_run.call_args_list]
    assert "secret-remover" in names
