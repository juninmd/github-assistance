"""Every issue/PR this app creates or shepherds must be assigned to the owner."""
import subprocess
from unittest.mock import MagicMock, patch

from github import GithubException

from src.agents import utils
from src.agents.base_agent import BaseAgent
from src.agents.interface_developer.agent import InterfaceDeveloperAgent
from src.agents.opencode_local import run_opencode_task
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.agents.project_creator.agent import ProjectCreatorAgent
from src.agents.secret_remover import git_utils


def _item(assignees=()):
    item = MagicMock()
    item.assignees = [MagicMock(login=login) for login in assignees]
    return item


def test_assign_owner_adds_login():
    item = _item()
    assert utils.assign_owner(item, "juninmd") is True
    item.add_to_assignees.assert_called_once_with("juninmd")


def test_assign_owner_falls_back_to_github_owner_env(monkeypatch):
    monkeypatch.setenv("GITHUB_OWNER", "someone")
    item = _item()
    utils.assign_owner(item)
    item.add_to_assignees.assert_called_once_with("someone")


def test_assign_owner_skips_when_already_assigned_case_insensitive():
    item = _item(["JuninMD"])
    assert utils.assign_owner(item, "juninmd") is True
    item.add_to_assignees.assert_not_called()


def test_assign_owner_failure_is_logged_not_raised():
    item = _item()
    item.add_to_assignees.side_effect = GithubException(422, {"message": "nope"}, None)
    log = MagicMock()
    assert utils.assign_owner(item, "juninmd", log) is False
    assert log.call_args.args[1] == "WARNING"


def test_opencode_runner_pr_is_assigned_to_agent_target_owner(monkeypatch):
    monkeypatch.setenv("GITHUB_OWNER", "env-owner")
    agent = ProjectCreatorAgent.__new__(ProjectCreatorAgent)
    BaseAgent.__init__(agent, MagicMock(), MagicMock(), MagicMock(), MagicMock(), target_owner="owner-x")
    runner = agent._opencode
    pr = runner.github_client.get_repo.return_value.create_pull.return_value
    pr.assignees = []
    runner._open_pull_request("owner-x/repo", "b", "T", "out", "agent")
    pr.add_to_assignees.assert_called_once_with("owner-x")


def test_project_creator_roadmap_issues_are_assigned():
    with patch("src.agents.project_creator.agent.get_ai_client"):
        agent = ProjectCreatorAgent(MagicMock(), MagicMock(), MagicMock(), target_owner="owner-x")
    repo = MagicMock()
    repo.get_labels.return_value = []
    issue = repo.create_issue.return_value
    issue.assignees = []
    agent._create_roadmap_backlog(repo, ["Add login"])
    issue.add_to_assignees.assert_called_once_with("owner-x")


def test_interface_developer_issue_is_assigned():
    agent = InterfaceDeveloperAgent(MagicMock(), MagicMock(), MagicMock(), target_owner="owner-x")
    agent._get_ai_client = MagicMock(return_value=None)
    repo = MagicMock()
    issue = repo.create_issue.return_value
    issue.assignees = []
    agent.create_ui_improvement_issue("owner-x/repo", {"repo_obj": repo, "improvements": ["x"]})
    issue.add_to_assignees.assert_called_once_with("owner-x")


@patch("src.agents.opencode_local._run_git")
@patch("src.agents.opencode_local.proc_run")
@patch("src.agents.opencode_local.tempfile.TemporaryDirectory")
def test_opencode_local_pr_is_assigned(mock_tmp, mock_run, _git, monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_OWNER", "juninmd")
    monkeypatch.setenv("GITHUB_TOKEN", "fake")
    mock_tmp.return_value.__enter__.return_value = str(tmp_path)
    mock_run.return_value = subprocess.CompletedProcess([], 0, "M file", "")
    _git.return_value = subprocess.CompletedProcess([], 0, "M file", "")
    github_client = MagicMock()
    pr = github_client.get_repo.return_value.create_pull.return_value
    pr.assignees = []
    result = run_opencode_task(github_client, "juninmd/repo", "do", "T", "main", MagicMock())
    assert result["status"] == "task_created", result
    pr.add_to_assignees.assert_called_once_with("juninmd")


@patch("src.agents.secret_remover.git_utils.Github")
@patch("src.agents.secret_remover.git_utils.proc_run")
def test_secret_remover_allowlist_pr_is_assigned(_run, mock_github, monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_OWNER", "juninmd")
    pr = mock_github.return_value.get_repo.return_value.create_pull.return_value
    pr.assignees = []
    finding = {"rule_id": "r", "file": "f", "commit": "c", "secret": "s", "line": 1}
    assert git_utils.apply_allowlist_locally("juninmd/repo", [finding], str(tmp_path), "t", MagicMock())
    pr.add_to_assignees.assert_called_once_with("juninmd")


def test_pr_assistant_assigns_every_processed_pr_even_when_skipped():
    with patch("src.agents.pr_assistant.agent.get_ai_client"):
        agent = PRAssistantAgent(MagicMock(), MagicMock(), MagicMock(), MagicMock(), target_owner="owner-x")
    pr = MagicMock()
    pr.assignees = []
    agent._skip_young_pr = MagicMock(return_value=True)
    agent._process_pr(pr, {"skipped": []})
    pr.add_to_assignees.assert_called_once_with("owner-x")
