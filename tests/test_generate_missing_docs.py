import os
import sys
import pytest
import responses
from unittest.mock import MagicMock, patch
from github.GithubException import UnknownObjectException

# Add scripts directory to path to import generate_missing_docs
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import generate_missing_docs

@pytest.fixture
def mock_github():
    with patch("generate_missing_docs.Github") as mock_g:
        mock_instance = MagicMock()
        mock_g.return_value = mock_instance
        
        mock_user = MagicMock()
        mock_instance.get_user.return_value = mock_user
        
        yield mock_user

@responses.activate
def test_generate_content_success():
    responses.add(
        responses.POST,
        generate_missing_docs.OLLAMA_URL,
        json={"response": "Generated Markdown"},
        status=200
    )
    result = generate_missing_docs.generate_content("test prompt")
    assert result == "Generated Markdown"

@responses.activate
def test_generate_content_failure():
    responses.add(
        responses.POST,
        generate_missing_docs.OLLAMA_URL,
        status=500
    )
    result = generate_missing_docs.generate_content("test prompt")
    assert result == ""

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

@patch.dict(os.environ, {}, clear=True)
def test_main_no_token(capsys):
    generate_missing_docs.main()
    captured = capsys.readouterr()
    assert "is not set" in captured.out

@patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"})
@patch("generate_missing_docs.generate_readme_content")
@patch("generate_missing_docs.generate_agents_content")
def test_main_with_missing_files(mock_gen_agents, mock_gen_readme, mock_github, capsys):
    mock_gen_readme.return_value = "Fake README"
    mock_gen_agents.return_value = "Fake AGENTS"

    mock_repo = MagicMock()
    mock_repo.full_name = "user/repo1"
    mock_repo.name = "repo1"
    mock_repo.description = "desc1"
    mock_repo.archived = False
    mock_repo.default_branch = "main"

    # Simulate both files missing
    def mock_get_contents(path):
        raise UnknownObjectException(status=404, data="Not Found")
        
    mock_repo.get_contents.side_effect = mock_get_contents
    mock_github.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()
    
    # Assert created both files
    assert mock_repo.create_file.call_count == 2
    create_calls = mock_repo.create_file.call_args_list
    assert create_calls[0].kwargs["path"] == "README.md"
    assert create_calls[1].kwargs["path"] == "AGENTS.md"

@patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"})
def test_main_archived_repo(mock_github):
    mock_repo = MagicMock()
    mock_repo.archived = True
    mock_github.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()
    mock_repo.get_contents.assert_not_called()

@patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"})
def test_main_files_exist(mock_github):
    mock_repo = MagicMock()
    mock_repo.archived = False
    # get_contents returning normally means files exist
    mock_repo.get_contents.return_value = MagicMock()
    mock_github.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()
    mock_repo.create_file.assert_not_called()

@patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"})
@patch("generate_missing_docs.generate_readme_content")
def test_main_ollama_empty(mock_gen_readme, mock_github, capsys):
    mock_gen_readme.return_value = "" # simulate ollama error/empty
    
    mock_repo = MagicMock()
    mock_repo.archived = False
    
    def mock_get_contents(path):
        if path == "README.md":
            raise UnknownObjectException(status=404, data="Not Found")
        return MagicMock() # AGENTS.md exists
        
    mock_repo.get_contents.side_effect = mock_get_contents
    mock_github.get_repos.return_value = [mock_repo]

    generate_missing_docs.main()
    
    mock_repo.create_file.assert_not_called()
    captured = capsys.readouterr()
    assert "empty content" in captured.out
