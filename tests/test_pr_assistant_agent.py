from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.agents.pr_assistant.agent import PRAssistantAgent


@pytest.fixture
def mock_agent():
    with patch("src.agents.pr_assistant.agent.get_ai_client"):
        agent = PRAssistantAgent(
            github_client=MagicMock(),
            jules_client=MagicMock(),
            telegram=MagicMock(),
            allowlist=MagicMock(),
            target_owner="test_owner",
            min_pr_age_minutes=10,
        )
        return agent


def test_properties(mock_agent):
    mock_agent.get_instructions_section = MagicMock()
    mock_agent.get_instructions_section.side_effect = ["persona", "mission"]
    assert mock_agent.persona == "persona"
    assert mock_agent.mission == "mission"


def test_pr_assistant_ignores_allowlist(mock_agent):
    assert mock_agent.uses_repository_allowlist() is False


def test_is_trusted_author(mock_agent):
    assert mock_agent._is_trusted_author("juninmd") is True
    assert mock_agent._is_trusted_author("dependabot[bot]") is True
    assert mock_agent._is_trusted_author("unknown") is False


def test_is_pr_old_enough(mock_agent):
    pr = MagicMock()

    # No created_at
    pr.created_at = None
    assert mock_agent._is_pr_old_enough(pr) is True

    # Old PR
    pr.created_at = datetime.now(UTC) - timedelta(minutes=15)
    assert mock_agent._is_pr_old_enough(pr) is True

    # Young PR
    pr.created_at = datetime.now(UTC) - timedelta(minutes=5)
    assert mock_agent._is_pr_old_enough(pr) is False


def test_get_pr_from_ref(mock_agent):
    pr = MagicMock()
    repo = MagicMock()
    repo.get_pull.return_value = pr
    mock_agent.github_client.get_repo.return_value = repo

    res = mock_agent._get_pr_from_ref("owner/repo#123")
    assert res == [pr]
    mock_agent.github_client.get_repo.assert_called_with("owner/repo")
    repo.get_pull.assert_called_with(123)


def test_get_pr_from_ref_exception(mock_agent):
    mock_agent.github_client.get_repo.side_effect = Exception("API error")
    res = mock_agent._get_pr_from_ref("owner/repo#123")
    assert res == []


def test_get_prs_to_process_with_ref(mock_agent):
    mock_agent.pr_ref = "owner/repo#123"
    mock_agent._get_pr_from_ref = MagicMock(return_value=["pr"])
    res = mock_agent._get_prs_to_process()
    assert res == ["pr"]


def test_get_prs_to_process_no_ref(mock_agent):
    mock_agent.pr_ref = None
    mock_agent.github_client.search_prs.return_value = ["issue1", "issue2"]
    mock_agent.github_client.get_pr_from_issue.side_effect = ["pr1", Exception("API error")]

    res = mock_agent._get_prs_to_process()
    assert res == ["pr1"]


@patch("src.agents.pr_assistant.agent.build_and_send_summary")
def test_run(mock_build, mock_agent):
    pr1 = MagicMock()
    pr1.number = 1
    pr1.title = "PR 1"

    pr2 = MagicMock()
    pr2.number = 2
    pr2.title = "PR 2"

    mock_agent._get_prs_to_process = MagicMock(return_value=[pr1, pr2])

    def mock_process(pr, results):
        if pr == pr1:
            results["merged"].append(pr)
        else:
            raise Exception("Process error")

    mock_agent._process_pr = MagicMock(side_effect=mock_process)

    results = mock_agent.run()

    assert pr1 in results["merged"]
    assert len(results["skipped"]) == 1
    assert results["skipped"][0]["reason"] == "error"
    assert results["skipped"][0]["error"] == "Process error"
    mock_build.assert_called_once()


def test_run_pr_missing_title(mock_agent):
    pr1 = MagicMock(spec=["number"])  # No title attribute
    pr1.number = 1

    mock_agent._get_prs_to_process = MagicMock(return_value=[pr1])

    def mock_process(pr, results):
        raise Exception("Process error")

    mock_agent._process_pr = MagicMock(side_effect=mock_process)

    results = mock_agent.run()

    assert len(results["skipped"]) == 1
    assert results["skipped"][0]["title"] == "Unknown Title"


def test_process_pr_too_young(mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=False)
    results = {"skipped": []}

    mock_agent._process_pr(pr, results)
    assert len(results["skipped"]) == 0  # No entry added for age skip


def test_process_pr_auto_merge_skip(mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    label = MagicMock()
    label.name = "auto-merge-skip"
    pr.get_labels.return_value = [label]

    results = {"skipped": []}
    mock_agent._process_pr(pr, results)

    assert len(results["skipped"]) == 1
    assert results["skipped"][0]["reason"] == "auto-merge-skip"


def test_process_pr_untrusted_author(mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    pr.get_labels.return_value = []
    pr.user.login = "unknown_user"

    results = {"skipped": []}
    mock_agent._process_pr(pr, results)

    assert len(results["skipped"]) == 1
    assert results["skipped"][0]["reason"] == "untrusted_author"


def test_try_accept_suggestions_success(mock_agent):
    pr = MagicMock()
    mock_agent.github_client.accept_review_suggestions.return_value = (True, "msg", 1)
    mock_agent._try_accept_suggestions(pr)


def test_try_accept_suggestions_failure(mock_agent):
    pr = MagicMock()
    mock_agent.github_client.accept_review_suggestions.return_value = (False, "err", 0)
    mock_agent._try_accept_suggestions(pr)


def test_try_accept_suggestions_exception(mock_agent):
    pr = MagicMock()
    mock_agent.github_client.accept_review_suggestions.side_effect = Exception("API error")
    mock_agent._try_accept_suggestions(pr)


@patch("src.agents.pr_assistant.agent.resolve_conflicts_autonomously")
def test_handle_conflicts_success(mock_resolve, mock_agent):
    pr = MagicMock()
    mock_resolve.return_value = (True, "resolved")
    mock_agent._notify_conflict_resolved = MagicMock()
    results = {"conflicts_resolved": [], "skipped": []}

    mock_agent._handle_conflicts(pr, results)

    assert len(results["conflicts_resolved"]) == 1
    assert len(results["skipped"]) == 0
    mock_agent._notify_conflict_resolved.assert_called_once_with(pr, "resolved")


def test_notify_conflict_resolved_success(mock_agent):
    pr = MagicMock()
    pr.number = 123
    pr.user.login = "author"
    pr.base.repo.full_name = "owner/repo"
    pr.html_url = "https://github.com/owner/repo/pull/123"
    msg = "resolved msg"

    mock_agent.telegram.escape = lambda x: x.replace("#", "\\#")

    mock_agent._notify_conflict_resolved(pr, msg)

    # Check GitHub comment
    mock_agent.github_client.comment_on_pr.assert_called_once()
    args, _ = mock_agent.github_client.comment_on_pr.call_args
    assert args[0] == pr
    assert "✅ **Conflitos de Merge Resolvidos**" in args[1]
    assert "@author" in args[1]
    assert "resolved msg" in args[1]

    # Check Telegram notification
    mock_agent.telegram.send_message.assert_called_once()
    t_args, t_kwargs = mock_agent.telegram.send_message.call_args
    assert "owner/repo" in t_args[0]
    assert "123" in t_args[0]
    assert t_kwargs.get("parse_mode") == "MarkdownV2"


def test_notify_conflict_resolved_github_exception(mock_agent):
    pr = MagicMock()
    pr.number = 123
    pr.user.login = "author"
    msg = "resolved msg"

    mock_agent.github_client.comment_on_pr.side_effect = Exception("GH API error")
    mock_agent.telegram.escape = lambda x: x.replace("#", "\\#")

    # Should not raise exception
    mock_agent._notify_conflict_resolved(pr, msg)

    # Telegram notification should still be sent even if GitHub comment fails
    mock_agent.telegram.send_message.assert_called_once()


def test_notify_conflict_resolved_telegram_exception(mock_agent):
    pr = MagicMock()
    pr.number = 123
    pr.user.login = "author"
    msg = "resolved msg"

    mock_agent.telegram.escape = lambda x: x.replace("#", "\\#")
    mock_agent.telegram.send_message.side_effect = Exception("Telegram API error")

    # Should not raise exception
    mock_agent._notify_conflict_resolved(pr, msg)

    # GitHub comment should have been attempted
    mock_agent.github_client.comment_on_pr.assert_called_once()


def test_notify_conflict_resolved_no_user(mock_agent):
    pr = MagicMock()
    pr.number = 123
    pr.user = None
    pr.base.repo.full_name = "owner/repo"
    msg = "resolved msg"

    mock_agent.telegram.escape = lambda x: x.replace("#", "\\#")

    mock_agent._notify_conflict_resolved(pr, msg)

    # Check GitHub comment uses "contributor"
    mock_agent.github_client.comment_on_pr.assert_called_once()
    args, _ = mock_agent.github_client.comment_on_pr.call_args
    assert "@contributor" in args[1]


@patch("src.agents.pr_assistant.agent.resolve_conflicts_autonomously")
def test_handle_conflicts_failure(mock_resolve, mock_agent):
    pr = MagicMock()
    mock_resolve.return_value = (False, "failed")
    mock_agent._notify_conflicts = MagicMock()
    results = {"conflicts_resolved": [], "skipped": []}

    mock_agent._handle_conflicts(pr, results)

    assert len(results["conflicts_resolved"]) == 0
    assert len(results["skipped"]) == 1
    mock_agent._notify_conflicts.assert_called_once_with(pr)


def test_notify_conflicts_already_notified(mock_agent):
    pr = MagicMock()
    comment = MagicMock()
    comment.body = "⚠️ **Conflitos de Merge Detectados**"
    pr.get_issue_comments.return_value = [comment]

    mock_agent._notify_conflicts(pr)
    mock_agent.github_client.comment_on_pr.assert_not_called()


def test_notify_conflicts_new(mock_agent):
    pr = MagicMock()
    pr.get_issue_comments.return_value = []

    mock_agent._notify_conflicts(pr)
    mock_agent.github_client.comment_on_pr.assert_called_once()


def test_notify_conflicts_exception(mock_agent):
    pr = MagicMock()
    pr.get_issue_comments.side_effect = Exception("API error")

    mock_agent._notify_conflicts(pr)
    mock_agent.github_client.comment_on_pr.assert_not_called()


def test_evaluate_comments_with_llm_no_comments(mock_agent):
    pr = MagicMock()
    pr.get_issue_comments.return_value = []

    should_merge, _reason = mock_agent._evaluate_comments_with_llm(pr)
    assert should_merge is True


def test_evaluate_comments_with_llm_no_human_comments(mock_agent):
    pr = MagicMock()
    comment = MagicMock()
    comment.user.login = "dependabot[bot]"
    pr.get_issue_comments.return_value = [comment]

    should_merge, _reason = mock_agent._evaluate_comments_with_llm(pr)
    assert should_merge is True


def test_evaluate_comments_with_llm_reject(mock_agent):
    pr = MagicMock()
    comment = MagicMock()
    comment.user.login = "human"
    comment.body = "This breaks everything"
    pr.get_issue_comments.return_value = [comment]

    mock_agent.ai_client.generate.return_value = "REJECT\nBreaks everything"

    should_merge, _reason = mock_agent._evaluate_comments_with_llm(pr)
    assert should_merge is False
    assert "REJECT" in _reason


def test_evaluate_comments_with_llm_merge(mock_agent):
    pr = MagicMock()
    comment = MagicMock()
    comment.user.login = "human"
    comment.body = "Looks fine"
    pr.get_issue_comments.return_value = [comment]

    mock_agent.ai_client.generate.return_value = "MERGE\nLooks fine"

    should_merge, _reason = mock_agent._evaluate_comments_with_llm(pr)
    assert should_merge is True


def test_evaluate_comments_with_llm_empty_response(mock_agent):
    pr = MagicMock()
    comment = MagicMock()
    comment.user.login = "human"
    pr.get_issue_comments.return_value = [comment]

    mock_agent.ai_client.generate.return_value = ""

    should_merge, _reason = mock_agent._evaluate_comments_with_llm(pr)
    assert should_merge is True


def test_evaluate_comments_with_llm_exception(mock_agent):
    pr = MagicMock()
    pr.get_issue_comments.side_effect = Exception("API error")

    should_merge, _reason = mock_agent._evaluate_comments_with_llm(pr)
    assert should_merge is True


def test_try_merge_rejected_by_llm(mock_agent):
    pr = MagicMock()
    mock_agent._evaluate_comments_with_llm = MagicMock(return_value=(False, "reject"))
    results = {"skipped": [], "merged": []}

    mock_agent._try_merge(pr, results)
    assert len(results["skipped"]) == 1
    assert len(results["merged"]) == 0


def test_try_merge_success(mock_agent):
    pr = MagicMock()
    mock_agent._evaluate_comments_with_llm = MagicMock(return_value=(True, "merge"))
    mock_agent.github_client.merge_pr.return_value = (True, "merged")
    results = {"skipped": [], "merged": []}

    mock_agent._try_merge(pr, results)
    assert len(results["merged"]) == 1
    assert len(results["skipped"]) == 0
    mock_agent.telegram.send_pr_notification.assert_called_once_with(pr)


def test_try_merge_failure(mock_agent):
    pr = MagicMock()
    mock_agent._evaluate_comments_with_llm = MagicMock(return_value=(True, "merge"))
    mock_agent.github_client.merge_pr.return_value = (False, "error")
    results = {"skipped": [], "merged": []}

    mock_agent._try_merge(pr, results)
    assert len(results["skipped"]) == 1
    assert len(results["merged"]) == 0


@patch("src.agents.pr_assistant.agent.has_existing_failure_comment")
@patch("src.agents.pr_assistant.agent.build_failure_comment")
def test_handle_pipeline_failure(mock_build, mock_has, mock_agent):
    pr = MagicMock()
    mock_has.return_value = False
    mock_build.return_value = "comment"
    status = {"state": "failure", "failed_checks": []}
    results = {"pipeline_failures": []}

    mock_agent._handle_pipeline_failure(pr, status, results)

    mock_agent.github_client.comment_on_pr.assert_called_once_with(pr, "comment")
    assert len(results["pipeline_failures"]) == 1


@patch("src.agents.pr_assistant.agent.check_pipeline_status")
def test_process_pr_mergeable_none(mock_check, mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    pr.get_labels.return_value = []
    pr.user.login = "juninmd"
    pr.mergeable = None

    results = {"skipped": []}
    mock_agent._process_pr(pr, results)

    assert len(results["skipped"]) == 1
    assert results["skipped"][0]["reason"] == "mergeable_unknown"


@patch("src.agents.pr_assistant.agent.check_pipeline_status")
def test_process_pr_not_mergeable(mock_check, mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    pr.get_labels.return_value = []
    pr.user.login = "juninmd"
    pr.mergeable = False

    mock_agent._handle_conflicts = MagicMock()
    results = {"skipped": []}

    mock_agent._process_pr(pr, results)

    mock_agent._handle_conflicts.assert_called_once()


@patch("src.agents.pr_assistant.agent.check_pipeline_status")
def test_process_pr_pipeline_success(mock_check, mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    pr.get_labels.return_value = []
    pr.user.login = "juninmd"
    pr.mergeable = True

    mock_check.return_value = {"state": "success"}
    mock_agent._try_merge = MagicMock()
    results = {"skipped": []}

    mock_agent._process_pr(pr, results)

    mock_agent._try_merge.assert_called_once()


@patch("src.agents.pr_assistant.agent.check_pipeline_status")
def test_process_pr_pipeline_failure(mock_check, mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    pr.get_labels.return_value = []
    pr.user.login = "juninmd"
    pr.mergeable = True

    mock_check.return_value = {"state": "failure"}
    mock_agent._handle_pipeline_failure = MagicMock()
    results = {"skipped": []}

    mock_agent._process_pr(pr, results)

    mock_agent._handle_pipeline_failure.assert_called_once()


@patch("src.agents.pr_assistant.agent.check_pipeline_status")
def test_process_pr_pipeline_pending(mock_check, mock_agent):
    pr = MagicMock()
    mock_agent._is_pr_old_enough = MagicMock(return_value=True)
    pr.get_labels.return_value = []
    pr.user.login = "juninmd"
    pr.mergeable = True

    mock_check.return_value = {"state": "pending"}
    results = {"skipped": []}

    mock_agent._process_pr(pr, results)

    assert len(results["skipped"]) == 1
    assert "pipeline_pending" in results["skipped"][0]["reason"]
