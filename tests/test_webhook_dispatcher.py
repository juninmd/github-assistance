import pytest

from src.config.settings import Settings
from src.queue.store import JobStore
from src.webhooks.dispatcher import _installation_token, enqueue_pr, extract_pr_refs


def test_incomplete_app_auth_fails_loudly_instead_of_using_pat():
    settings = Settings(github_token="owner-pat", github_app_id=1)
    with pytest.raises(ValueError, match="incomplete"):
        _installation_token(settings)


def test_extract_pr_refs_from_pull_request():
    payload = {
        "repository": {"full_name": "juninmd/repo"},
        "pull_request": {"number": 12},
    }
    assert extract_pr_refs("pull_request", payload) == ["juninmd/repo#12"]


def test_extract_pr_refs_from_check_suite():
    payload = {
        "repository": {"full_name": "juninmd/repo"},
        "check_suite": {"pull_requests": [{"number": 9}, {"number": 7}]},
    }
    assert extract_pr_refs("check_suite", payload) == ["juninmd/repo#7", "juninmd/repo#9"]


def test_extract_pr_ref_from_issue_comment_only_for_pr():
    payload = {
        "repository": {"full_name": "juninmd/repo"},
        "issue": {"number": 5, "pull_request": {"url": "https://api.github.com/pr/5"}},
    }
    assert extract_pr_refs("issue_comment", payload) == ["juninmd/repo#5"]
    payload["issue"].pop("pull_request")
    assert extract_pr_refs("issue_comment", payload) == []


def test_enqueue_persists_and_deduplicates_by_key(tmp_path):
    settings = Settings(
        github_token="token",
        webhook_database_path=str(tmp_path / "queue.db"),
    )
    store = JobStore(settings.webhook_database_path)
    store.initialize()
    assert enqueue_pr(settings, "juninmd/repo#77") is True
    assert enqueue_pr(settings, "juninmd/repo#77") is True  # idempotent, no duplicate
    jobs = store.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["key"] == "juninmd/repo#77"
