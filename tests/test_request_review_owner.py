"""Tests for request_review_owner and BaseAgent PR review requests."""
from unittest.mock import MagicMock

from github import GithubException

from src.agents import utils
from src.agents.base_agent import BaseAgent


def _pr(requested=(), author=None):
    pr = MagicMock()
    pr.requested_reviewers = [MagicMock(login=login) for login in requested]
    if author:
        pr.user = MagicMock(login=author)
    else:
        pr.user = None
    return pr


def test_request_review_owner_adds_login():
    pr = _pr()
    assert utils.request_review_owner(pr, "juninmd") is True
    pr.create_review_request.assert_called_once_with(reviewers=["juninmd"])


def test_request_review_owner_falls_back_to_github_owner_env(monkeypatch):
    monkeypatch.setenv("GITHUB_OWNER", "someone")
    pr = _pr()
    assert utils.request_review_owner(pr) is True
    pr.create_review_request.assert_called_once_with(reviewers=["someone"])


def test_request_review_owner_skips_when_author_is_owner():
    pr = _pr(author="juninmd")
    assert utils.request_review_owner(pr, "juninmd") is False
    pr.create_review_request.assert_not_called()


def test_request_review_owner_skips_when_already_requested_case_insensitive():
    pr = _pr(["JuninMD"])
    assert utils.request_review_owner(pr, "juninmd") is True
    pr.create_review_request.assert_not_called()


def test_request_review_owner_skips_when_not_a_pr():
    issue = object()
    assert utils.request_review_owner(issue, "juninmd") is False


def test_request_review_owner_failure_is_logged_not_raised():
    pr = _pr()
    pr.create_review_request.side_effect = GithubException(422, {"message": "nope"}, None)
    log = MagicMock()
    assert utils.request_review_owner(pr, "juninmd", log) is False
    assert log.call_args.args[1] == "WARNING"


def test_base_agent_open_pull_request_assigns_and_requests_review():
    class TestAgent(BaseAgent):
        @property
        def persona(self):
            return "Test"

        @property
        def mission(self):
            return "Test"

        def run(self):
            return {}

    github_client = MagicMock()
    repo = github_client.get_repo.return_value
    repo.default_branch = "main"
    pr = repo.create_pull.return_value
    pr.assignees = []
    pr.requested_reviewers = []
    pr.user = None

    agent = TestAgent(MagicMock(), github_client, MagicMock(), target_owner="juninmd")
    url = agent._open_pull_request("owner/repo", "feat", "Title", "out")

    assert url == pr.html_url
    pr.add_to_assignees.assert_called_once_with("juninmd")
    pr.create_review_request.assert_called_once_with(reviewers=["juninmd"])
