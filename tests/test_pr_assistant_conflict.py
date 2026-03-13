import subprocess
from unittest.mock import MagicMock, patch

from src.agents.pr_assistant.conflict_resolver import (
    _get_conflicted_files,
    _resolve_file_conflicts,
    _run_git,
    resolve_conflicts_autonomously,
)


@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
def test_run_git_success(mock_run):
    mock_run.return_value.returncode = 0
    result = _run_git(["git", "status"], "/tmp")
    assert result.returncode == 0
    mock_run.assert_called_once()


@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
def test_run_git_failure(mock_run):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "error"
    result = _run_git(["git", "status"], "/tmp")
    assert result.returncode == 1


@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
def test_get_conflicted_files(mock_run):
    mock_run.return_value.stdout = "file1.txt\nfile2.txt\n"
    files = _get_conflicted_files("/tmp")
    assert files == ["file1.txt", "file2.txt"]


def test_resolve_file_conflicts_success():
    client = MagicMock()
    client.resolve_conflict.return_value = "resolved content"
    content = "<<<<<<< HEAD\ncontent1\n=======\ncontent2\n>>>>>>> branch"
    result = _resolve_file_conflicts(content, client)
    assert result == "resolved content"


def test_resolve_file_conflicts_failure_has_markers():
    client = MagicMock()
    client.resolve_conflict.return_value = "<<<<<<< HEAD\nstill conflicted\n=======\n>>>>>>> branch"
    content = "<<<<<<< HEAD\ncontent1\n=======\ncontent2\n>>>>>>> branch"
    result = _resolve_file_conflicts(content, client)
    assert result is None


def test_resolve_file_conflicts_exception():
    client = MagicMock()
    client.resolve_conflict.side_effect = Exception("AI Error")
    content = "<<<<<<< HEAD\ncontent1\n=======\ncontent2\n>>>>>>> branch"
    result = _resolve_file_conflicts(content, client)
    assert result is None


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
@patch("src.agents.pr_assistant.conflict_resolver._get_conflicted_files")
@patch("src.agents.pr_assistant.conflict_resolver.os.path.exists")
@patch("builtins.open")
def test_resolve_conflicts_autonomously_success(
    mock_open, mock_exists, mock_get_conflicts, mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_merge_result = MagicMock()
    mock_merge_result.returncode = 1
    mock_sub_run.return_value = mock_merge_result

    mock_get_conflicts.return_value = ["file1.txt"]
    mock_exists.return_value = True

    mock_file = MagicMock()
    mock_file.read.return_value = "<<<<<<< HEAD\ncontent1\n=======\ncontent2\n>>>>>>> main"
    mock_open.return_value.__enter__.return_value = mock_file

    mock_client = MagicMock()
    mock_client.resolve_conflict.return_value = "resolved content"
    mock_get_ai.return_value = mock_client

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is True
    assert "Resolved 1 conflict" in msg
    mock_run_git.assert_any_call(["git", "push", "origin", "feature"], cwd="/tmp/dir")


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
def test_resolve_conflicts_autonomously_no_conflicts(
    mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_merge_result = MagicMock()
    mock_merge_result.returncode = 0
    mock_sub_run.return_value = mock_merge_result

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is True
    assert "No conflicts found" in msg


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
@patch("src.agents.pr_assistant.conflict_resolver._get_conflicted_files")
def test_resolve_conflicts_autonomously_no_files_detected(
    mock_get_conflicts, mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_merge_result = MagicMock()
    mock_merge_result.returncode = 1
    mock_sub_run.return_value = mock_merge_result

    mock_get_conflicts.return_value = []

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is False
    assert "no conflicted files" in msg


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
def test_resolve_conflicts_autonomously_timeout(
    mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_sub_run.side_effect = subprocess.TimeoutExpired(cmd="git merge", timeout=120)

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is False
    assert "timed out" in msg


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
def test_resolve_conflicts_autonomously_exception(
    mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_sub_run.side_effect = Exception("Git error")

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is False
    assert "Error resolving conflicts" in msg


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
@patch("src.agents.pr_assistant.conflict_resolver._get_conflicted_files")
@patch("src.agents.pr_assistant.conflict_resolver.os.path.exists")
@patch("builtins.open")
def test_resolve_conflicts_autonomously_no_markers_and_unresolved(
    mock_open, mock_exists, mock_get_conflicts, mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_merge_result = MagicMock()
    mock_merge_result.returncode = 1
    mock_sub_run.return_value = mock_merge_result

    mock_get_conflicts.return_value = ["file1.txt", "file2.txt", "file3.txt"]
    mock_exists.side_effect = [False, True, True]  # file1 doesn't exist

    mock_file1 = MagicMock()
    mock_file1.read.return_value = "clean content without markers"

    mock_file2 = MagicMock()
    mock_file2.read.return_value = "<<<<<<< HEAD\ncontent1\n=======\ncontent2\n>>>>>>> main"

    mock_open.side_effect = [
        MagicMock(__enter__=MagicMock(return_value=mock_file1)),
        MagicMock(__enter__=MagicMock(return_value=mock_file2)),
    ]

    mock_client = MagicMock()
    mock_client.resolve_conflict.return_value = None  # AI fails to resolve
    mock_get_ai.return_value = mock_client

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is True  # One file had no markers, so it was "resolved"
    assert "Resolved 1 conflict" in msg
    mock_run_git.assert_any_call(["git", "add", "file2.txt"], cwd="/tmp/dir")  # Added by the no-markers block


@patch("src.agents.pr_assistant.conflict_resolver.get_ai_client")
@patch("src.agents.pr_assistant.conflict_resolver.tempfile.TemporaryDirectory")
@patch("src.agents.pr_assistant.conflict_resolver._run_git")
@patch("src.agents.pr_assistant.conflict_resolver.subprocess.run")
@patch("src.agents.pr_assistant.conflict_resolver._get_conflicted_files")
@patch("src.agents.pr_assistant.conflict_resolver.os.path.exists")
@patch("builtins.open")
def test_resolve_conflicts_autonomously_unresolved_zero(
    mock_open, mock_exists, mock_get_conflicts, mock_sub_run, mock_run_git, mock_tempdir, mock_get_ai
):
    pr = MagicMock()
    pr.head.repo.full_name = "owner/repo"
    pr.base.repo.full_name = "owner/repo"
    pr.base.ref = "main"
    pr.head.ref = "feature"

    mock_tempdir.return_value.__enter__.return_value = "/tmp/dir"

    mock_merge_result = MagicMock()
    mock_merge_result.returncode = 1
    mock_sub_run.return_value = mock_merge_result

    mock_get_conflicts.return_value = ["file1.txt"]
    mock_exists.return_value = True

    mock_file1 = MagicMock()
    mock_file1.read.return_value = "<<<<<<< HEAD\ncontent\n=======\n>>>>>>> main"

    mock_open.return_value.__enter__.return_value = mock_file1

    mock_client = MagicMock()
    mock_client.resolve_conflict.return_value = None  # AI fails to resolve
    mock_get_ai.return_value = mock_client

    success, msg = resolve_conflicts_autonomously(pr)

    assert success is False
    assert "could not resolve any conflicts" in msg
