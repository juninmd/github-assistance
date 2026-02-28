import subprocess
from datetime import datetime
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.agents.pr_assistant.agent import PRAssistantAgent


@pytest.fixture
def mock_agent():
    jules_client = MagicMock()
    github_client = MagicMock()
    allowlist = MagicMock()
    agent = PRAssistantAgent(
        jules_client=jules_client,
        github_client=github_client,
        allowlist=allowlist,
        target_owner="owner",
        ai_provider="ollama" # Mocked client
    )
    agent.log = MagicMock()
    agent.ai_client.resolve_conflict = MagicMock()
    return agent

# ... (Previous tests kept)

def test_resolve_conflicts_mixed_files(mock_agent):
    pr = MagicMock()
    pr.head.repo.clone_url = "https://github.com/owner/repo.git"
    pr.base.repo.clone_url = "https://github.com/owner/repo.git"
    pr.head.ref = "feature-branch"
    pr.base.ref = "main"

    with patch("tempfile.TemporaryDirectory") as mock_temp:
        mock_temp.return_value.__enter__.return_value = "/tmp/repo"

        with patch("subprocess.run") as mock_run, \
             patch("subprocess.check_output") as mock_check_output:

            def run_side_effect(args, **kwargs):
                if args and len(args) > 1 and args[1] == "merge":
                    raise subprocess.CalledProcessError(1, args)
                return MagicMock()
            mock_run.side_effect = run_side_effect

            mock_check_output.return_value = b"binary_file.png\ntext_file.txt\n"

            def open_side_effect(filename, *args, **kwargs):
                f = MagicMock()
                if "binary_file.png" in str(filename):
                    f.__enter__.return_value.read.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
                elif "text_file.txt" in str(filename):
                    f.__enter__.return_value.read.return_value = "clean content\n"
                else:
                    f.__enter__.return_value.read.return_value = ""
                return f

            with patch("builtins.open", side_effect=open_side_effect):

                mock_agent.ai_client.resolve_conflict.return_value = "resolved"

                mock_agent.resolve_conflicts_autonomously(pr)

                log_calls = [c[0][0] for c in mock_agent.log.call_args_list]

                assert any("Skipping binary file" in str(msg) and "binary_file.png" in str(msg) for msg in log_calls)
                assert any("No markers found in text_file.txt" in str(msg) for msg in log_calls)
                mock_agent.ai_client.resolve_conflict.assert_not_called()

def test_handle_pipeline_failure_ai_exception(mock_agent):
    pr = MagicMock()
    pr.number = 123
    failure_desc = "Test Failure"

    mock_agent.ai_client.generate_pr_comment = MagicMock(side_effect=Exception("AI Error"))
    mock_agent.github_client.get_issue_comments.return_value = []

    mock_agent.handle_pipeline_failure(pr, failure_desc)

    log_calls = [c[0][0] for c in mock_agent.log.call_args_list]
    assert any("AI Client failed to generate comment: AI Error" in str(msg) for msg in log_calls)
    pr.create_issue_comment.assert_called()

def test_check_pipeline_status_error(mock_agent):
    pr = MagicMock()
    pr.number = 123
    pr.get_commits.side_effect = Exception("API Error")
    result = mock_agent.check_pipeline_status(pr)
    assert result["success"] is False
    assert result["reason"] == "error"

def test_notify_conflicts_error_handling(mock_agent):
    pr = MagicMock()
    pr.number = 123
    mock_agent.github_client.get_issue_comments.side_effect = Exception("Comment Fetch Error")
    mock_agent.notify_conflicts(pr)
    log_calls = [c[0][0] for c in mock_agent.log.call_args_list]
    assert any("Error checking existing comments" in str(msg) for msg in log_calls)

    mock_agent.github_client.get_issue_comments.side_effect = None
    mock_agent.github_client.get_issue_comments.return_value = []
    pr.create_issue_comment.side_effect = Exception("Post Error")
    mock_agent.notify_conflicts(pr)
    log_calls = [c[0][0] for c in mock_agent.log.call_args_list]
    assert any("Failed to post conflict notification" in str(msg) for msg in log_calls)

def test_handle_pipeline_failure_comment_check_error(mock_agent):
    pr = MagicMock()
    pr.number = 123
    mock_agent.github_client.get_issue_comments.side_effect = Exception("Check Error")
    mock_agent.ai_client.generate_pr_comment = MagicMock(return_value="Comment")
    mock_agent.handle_pipeline_failure(pr, "desc")
    log_calls = [c[0][0] for c in mock_agent.log.call_args_list]
    assert any("Error checking existing comments" in str(msg) for msg in log_calls)

def test_run_top_level_exception(mock_agent):
    mock_agent._get_prs_to_process = MagicMock(side_effect=Exception("Scan Error"))
    result = mock_agent.run()
    assert result["status"] == "error"

def test_run_pr_processing_exception(mock_agent):
    mock_agent._get_prs_to_process = MagicMock(return_value=[{"repository": "repo", "number": 123}])
    mock_agent.github_client.get_pr.side_effect = Exception("Get PR Error")
    result = mock_agent.run()
    assert len(result["skipped"]) == 1

def test_check_pipeline_status_legacy_unknown(mock_agent):
    pr = MagicMock()
    commit = MagicMock()
    combined = MagicMock()
    combined.state = "timed_out"
    combined.total_count = 1
    commit.get_combined_status.return_value = combined
    pr.get_commits.return_value.reversed = [commit]
    result = mock_agent.check_pipeline_status(pr)
    assert result["reason"] == "pending"
    assert "Legacy status is timed_out" in result["details"]

def test_check_pipeline_status_annotations_error(mock_agent):
    pr = MagicMock()
    commit = MagicMock()
    commit.get_combined_status.return_value.state = "success"
    run = MagicMock()
    run.status = "completed"
    run.conclusion = "failure"
    run.name = "Job"
    run.get_annotations.side_effect = Exception("Annotation API Error")
    commit.get_check_runs.return_value = [run]
    pr.get_commits.return_value.reversed = [commit]
    result = mock_agent.check_pipeline_status(pr)
    assert result["success"] is False

def test_resolve_conflicts_auto_merge_success(mock_agent):
    pr = MagicMock()
    pr.head.repo.clone_url = "https://github.com/owner/repo.git"
    pr.base.repo.clone_url = "https://github.com/owner/repo.git"
    with patch("tempfile.TemporaryDirectory") as mock_temp:
        mock_temp.return_value.__enter__.return_value = "/tmp/repo"
        with patch("subprocess.run") as mock_run:
            result = mock_agent.resolve_conflicts_autonomously(pr)
            assert result is True
            push_called = any(call[0][0] == ['git', 'push'] for call in mock_run.call_args_list)
            assert push_called

def test_check_pipeline_status_soft_failure(mock_agent):
    pr = MagicMock()
    commit = MagicMock()
    commit.get_combined_status.return_value.state = "success"
    run = MagicMock()
    run.status = "completed"
    run.conclusion = "failure"
    run.name = "Deploy"
    annotation = MagicMock()
    annotation.message = "Billing limit reached"
    run.get_annotations.return_value = [annotation]
    commit.get_check_runs.return_value = [run]
    pr.get_commits.return_value.reversed = [commit]
    result = mock_agent.check_pipeline_status(pr)
    assert result["success"] is True

def test_check_pipeline_status_legacy_soft_failures(mock_agent):
    pr = MagicMock()
    commit = MagicMock()
    combined = MagicMock()
    combined.state = "failure"
    combined.total_count = 1
    s1 = MagicMock()
    s1.state = "failure"
    s1.context = "netlify/deploy"
    s1.description = "Deploy failed"
    combined.statuses = [s1]
    commit.get_combined_status.return_value = combined
    pr.get_commits.return_value.reversed = [commit]
    result = mock_agent.check_pipeline_status(pr)
    assert result["success"] is True
    s2 = MagicMock()
    s2.state = "failure"
    s2.context = "ci/billing"
    s2.description = "spending limit reached"
    combined.statuses = [s2]
    commit.get_combined_status.return_value = combined
    result = mock_agent.check_pipeline_status(pr)
    assert result["success"] is True

def test_has_commit_suggestion_edge_cases(mock_agent):
    pr = MagicMock()
    pr.body = None
    assert mock_agent._has_commit_suggestion_in_pr_message(pr) is False
    pr.body = ""
    assert mock_agent._has_commit_suggestion_in_pr_message(pr) is False
    pr.body = "Please accept this commit suggestion"
    assert mock_agent._has_commit_suggestion_in_pr_message(pr) is True

    class NoBody:
        pass
    assert mock_agent._has_commit_suggestion_in_pr_message(NoBody()) is False

def test_escape_telegram_empty(mock_agent):
    assert mock_agent._escape_telegram(None) is None
    assert mock_agent._escape_telegram("") == ""

def test_get_pr_age_minutes_naive(mock_agent):
    pr = MagicMock()
    pr.created_at = datetime(2023, 1, 1, 12, 0, 0)
    age = mock_agent.get_pr_age_minutes(pr)
    assert age > 0

def test_get_prs_to_process_variations(mock_agent):
    # 1. owner/repo#123
    res = mock_agent._get_prs_to_process("owner/repo#123")
    assert res[0]["repository"] == "owner/repo"
    assert res[0]["number"] == 123

    # 2. repo#123
    res = mock_agent._get_prs_to_process("repo#123")
    assert res[0]["repository"] == "owner/repo" # target_owner/repo
    assert res[0]["number"] == 123

    # 3. 123 (just number)
    # This triggers search
    mock_issue = MagicMock()
    mock_issue.number = 123
    mock_issue.repository.full_name = "owner/repo"
    mock_agent.github_client.search_prs.return_value = [mock_issue]

    res = mock_agent._get_prs_to_process("123")
    assert res[0]["number"] == 123
    assert res[0]["repository"] == "owner/repo"
    mock_agent.github_client.search_prs.assert_called()
