from src.webhooks.dispatcher import extract_pr_refs


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
