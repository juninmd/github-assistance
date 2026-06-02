from unittest.mock import MagicMock, patch

from src.vibe_code_client import VibeCodeClient


def _response(status: int, payload: dict):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("src.vibe_code_client.requests.request")
def test_create_opencode_task_reuses_existing_repo(mock_request):
    mock_request.side_effect = [
        _response(200, {"data": [{"id": "r1", "url": "https://github.com/owner/repo.git"}]}),
        _response(201, {"data": {"id": "t1", "engine": "opencode"}}),
    ]
    client = VibeCodeClient(base_url="http://localhost:3000")

    result = client.create_opencode_task("owner/repo", "do work", "Fix it", "main")

    assert result == {
        "status": "task_created",
        "task_id": "t1",
        "task_url": "http://localhost:3000/tasks/t1",
        "repository": "owner/repo",
        "engine": "opencode",
    }
    _, _, task_kwargs = mock_request.mock_calls[1]
    assert task_kwargs["json"]["repoId"] == "r1"
    assert task_kwargs["json"]["engine"] == "opencode"
    assert task_kwargs["json"]["baseBranch"] == "main"


@patch("src.vibe_code_client.requests.request")
def test_create_opencode_task_creates_missing_repo(mock_request):
    mock_request.side_effect = [
        _response(200, {"data": []}),
        _response(201, {"data": {"id": "r2", "url": "https://github.com/owner/repo.git"}}),
        _response(201, {"data": {"id": "t2", "engine": "opencode"}}),
    ]
    client = VibeCodeClient(base_url="http://localhost:3000/api")

    result = client.create_opencode_task("owner/repo", "do work", "Fix it")

    assert result["task_id"] == "t2"
    _, _, repo_kwargs = mock_request.mock_calls[1]
    assert repo_kwargs["json"] == {"url": "https://github.com/owner/repo.git"}
