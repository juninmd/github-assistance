import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests
from github.GithubException import GithubException, UnknownObjectException

# Add scripts directory to path to import generate_missing_docs
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import generate_missing_docs  # pyright: ignore[reportMissingImports]


@pytest.fixture(autouse=True)
def setup_env():
    with patch.dict(os.environ, {"ENABLE_AI": "true"}):
        yield

@pytest.fixture
def mock_github_user():
    with patch("generate_missing_docs.Github") as mock_github:
        github_instance = MagicMock()
        mock_github.return_value = github_instance

        mock_user = MagicMock()
        github_instance.get_user.return_value = mock_user
        yield mock_user


@patch("generate_missing_docs.requests.post")
def test_generate_content_success(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Generated Markdown"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = generate_missing_docs.generate_content("test prompt")

    assert result == "Generated Markdown"


@patch("generate_missing_docs.requests.post")
def test_generate_content_failure(mock_post, capsys):
    mock_post.side_effect = requests.RequestException("failure")

    result = generate_missing_docs.generate_content("test prompt")

    assert result == ""
    assert "Error communicating with Ollama" in capsys.readouterr().out


@patch("generate_missing_docs.generate_content")
def test_generate_readme_content(mock_generate):
    mock_generate.return_value = "README content"

    result = generate_missing_docs.generate_readme_content("my-repo", "my desc", "file1.py\nfile2.txt")

    assert result == "README content"
    assert mock_generate.call_args[0][0].startswith("Generate a concise, professional README.md")
    assert "file1.py\nfile2.txt" in mock_generate.call_args[0][0]


@patch("generate_missing_docs.generate_content")
def test_generate_agents_content(mock_generate):
    mock_generate.return_value = "AGENTS content"

    result = generate_missing_docs.generate_agents_content()

    assert result == "AGENTS content"
    prompt = mock_generate.call_args[0][0]
    assert "DRY" in prompt
    assert "SOLID" in prompt

@patch.dict(os.environ, {"ENABLE_AI": "false"}, clear=True)
def test_main_ai_disabled(capsys):
    generate_missing_docs.main()
    captured = capsys.readouterr()
    assert "Skipping AI documentation generation (ENABLE_AI is false)." in captured.out

@patch.dict(os.environ, {"ENABLE_AI": "true"}, clear=True)
def test_main_no_token(capsys):
    generate_missing_docs.main()

    assert "GITHUB_TOKEN is not set" in capsys.readouterr().out


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
@patch("generate_missing_docs.generate_readme_content")
@patch("generate_missing_docs.generate_agents_content")
def test_main_with_missing_files(mock_gen_agents, mock_gen_readme, mock_github_user):
    mock_gen_readme.return_value = "Fake README"
    mock_gen_agents.return_value = "Fake AGENTS"

    mock_repo = MagicMock(
        full_name="user/repo1", name="repo1", description="desc1", archived=False, default_branch="main"
    )

    mock_file = MagicMock()
    mock_file.path = "some_file.py"

    mock_empty_file = MagicMock()
    mock_empty_file.path = ""

    def mock_get_contents(path):
        if path == "README.md" or path == "AGENTS.md":
            raise UnknownObjectException(status=404, data="Not Found")
        if path == "":
            return [mock_file, mock_empty_file]
        return None

    mock_repo.get_contents.side_effect = mock_get_contents
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    assert mock_repo.create_file.call_count == 2
    assert mock_repo.create_file.call_args_list[0].kwargs["path"] == "README.md"
    assert mock_repo.create_file.call_args_list[1].kwargs["path"] == "AGENTS.md"


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
def test_main_archived_repo(mock_github_user):
    mock_repo = MagicMock(archived=True)
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    mock_repo.get_contents.assert_not_called()


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
def test_main_files_exist(mock_github_user):
    mock_repo = MagicMock(archived=False)
    mock_repo.get_contents.return_value = MagicMock()
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    mock_repo.create_file.assert_not_called()


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
@patch("generate_missing_docs.generate_readme_content")
def test_main_ollama_empty(mock_gen_readme, mock_github_user, capsys):
    mock_gen_readme.return_value = ""

    mock_repo = MagicMock(archived=False)

    def mock_get_contents(path):
        if path == "README.md":
            raise UnknownObjectException(status=404, data="Not Found")
        return MagicMock()

    mock_repo.get_contents.side_effect = mock_get_contents
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    mock_repo.create_file.assert_not_called()
    assert "empty content" in capsys.readouterr().out


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
def test_main_empty_repo(mock_github_user, capsys):
    mock_repo = MagicMock(archived=False)
    mock_repo.get_contents.side_effect = GithubException(status=404, data={"message": "This repository is empty."})
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    mock_repo.create_file.assert_not_called()
    assert "Repository is empty, skipping." in capsys.readouterr().out


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
def test_main_github_exception_re_raised(mock_github_user):
    mock_repo = MagicMock(archived=False)
    mock_repo.get_contents.side_effect = GithubException(status=500, data={"message": "Internal Server Error"})
    mock_github_user.get_repos.return_value = [mock_repo]

    with pytest.raises(GithubException):
        generate_missing_docs.main()


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
@patch("generate_missing_docs.generate_readme_content")
def test_main_get_contents_unknown_exception(mock_gen_readme, mock_github_user, capsys):
    mock_gen_readme.return_value = "Fake README"

    mock_repo = MagicMock(full_name="user/repo1", name="repo1", description="desc1", archived=False, default_branch="main")

    def mock_get_contents(path):
        if path in {"README.md", "AGENTS.md"}:
            raise UnknownObjectException(status=404, data="Not Found")
        if path == "":
            raise Exception("Some generic error")
        return MagicMock()

    mock_repo.get_contents.side_effect = mock_get_contents
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    assert "Warning: failed to fetch repository contents: Some generic error" in capsys.readouterr().out


@patch.dict(os.environ, {"ENABLE_AI": "true", "GITHUB_TOKEN": "fake_token"})
@patch("generate_missing_docs.generate_readme_content")
@patch("generate_missing_docs.generate_agents_content")
def test_main_create_file_exception(mock_gen_agents, mock_gen_readme, mock_github_user, capsys):
    mock_gen_readme.return_value = "Fake README"
    mock_gen_agents.return_value = "Fake AGENTS"

    mock_repo = MagicMock(full_name="user/repo1", archived=False)
    mock_repo.get_contents.side_effect = UnknownObjectException(status=404, data="Not Found")
    mock_repo.create_file.side_effect = Exception("Create failed")
    mock_github_user.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()

    assert "Failed to create README.md: Create failed" in capsys.readouterr().out
