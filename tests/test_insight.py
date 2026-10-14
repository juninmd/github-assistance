"""Insight: explain why a PR was not merged (history + live policy)."""

from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.insight.explain import explain_pr, job_history
from src.queue.store import JobStore


def _settings(tmp_path) -> Settings:
    return Settings(
        github_token="token",
        webhook_database_path=str(tmp_path / "queue.db"),
    )


def test_job_history_returns_pr_rows(tmp_path):
    settings = _settings(tmp_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    store.enqueue("pr", "juninmd/repo#1", {"mode": "observe"})
    store.enqueue("pr", "juninmd/repo#2", {"mode": "autonomous"})
    rows = job_history(settings, "juninmd/repo#1")
    assert [r["key"] for r in rows] == ["juninmd/repo#1"]


def test_explain_pr_reports_reasons(tmp_path):
    import json

    autonomy_path = tmp_path / "autonomy.json"
    autonomy_path.write_text(
        json.dumps(
            {
                "repositories": {
                    "juninmd/repo": {"mode": "merge", "merge": True, "require_evidence": True}
                }
            }
        ),
        encoding="utf-8",
    )
    settings = _settings(tmp_path)
    settings.autonomy_policy_path = str(autonomy_path)
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    job_id, _ = store.enqueue("pr", "juninmd/repo#7", {"mode": "autonomous"})
    store.complete(
        job_id,
        "succeeded",
        decision="observed",
        next_action="observe",
    )

    pr = MagicMock()
    pr.state = "open"
    pr.merged_at = None
    pr.head.sha = "abc123"
    pr.mergeable = True

    status = {
        "state": "pending",
        "failed_checks": [],
        "pending_checks": ["ci"],
        "cancelled_checks": [],
        "success_checks": [],
        "has_evidence": True,
        "checks": {"total": 1, "success": 0, "failed": 0, "pending": 1, "cancelled": 0},
    }
    with (
        patch("src.insight.explain.check_pipeline_status", return_value=status),
        patch("src.insight.explain.GithubClient") as client_cls,
    ):
        client_cls.return_value.get_repo.return_value.get_pull.return_value = pr
        report = explain_pr(settings, "juninmd/repo#7")

    assert report["reasons"] == ["checks_pending"]
    assert report["decision"] == "wait"
    assert report["autonomy_mode"] == "merge"


def test_explain_pr_pr_unavailable(tmp_path):
    settings = _settings(tmp_path)
    with patch("src.insight.explain.GithubClient") as client_cls:
        client_cls.return_value.get_repo.side_effect = Exception("API down")
        report = explain_pr(settings, "juninmd/repo#9")
    assert any(r.startswith("pr_unavailable") for r in report["reasons"])
