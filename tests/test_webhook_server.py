import hashlib
import hmac
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.webhooks.server import create_app


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        github_token="unused",
        github_app_id=3982807,
        github_installation_id=138493700,
        github_app_private_key_path=str(tmp_path / "missing.pem"),
        github_webhook_secret="test-secret",
        webhook_database_path=str(tmp_path / "webhooks.db"),
    )


def _signature(body: bytes) -> str:
    digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_webhook_records_and_deduplicates(tmp_path):
    app = create_app(_settings(tmp_path))
    body = (
        b'{"action":"opened","number":1,"pull_request":{"number":1},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    headers = {
        "X-GitHub-Delivery": "delivery-1",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": _signature(body),
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        first = client.post("/webhooks/github", content=body, headers=headers)
        second = client.post("/webhooks/github", content=body, headers=headers)
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["pr_refs"] == ["juninmd/repo#1"]


def test_webhook_rejects_invalid_signature(tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=b"{}",
            headers={
                "X-GitHub-Delivery": "delivery-2",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
    assert response.status_code == 401


def test_unsupported_event_is_ignored(tmp_path):
    app = create_app(_settings(tmp_path))
    body = b"{}"
    with TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-3",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    assert response.json() == {"accepted": False, "reason": "unsupported_event"}


def test_autonomous_mode_dispatches_targeted_pr(tmp_path):
    settings = _settings(tmp_path)
    settings.automation_mode = "autonomous"
    app = create_app(settings)
    body = (
        b'{"action":"opened","number":8,"pull_request":{"number":8},'
        b'"repository":{"full_name":"juninmd/repo"}}'
    )
    with patch("src.webhooks.server.enqueue_pr") as enqueue, TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-autonomous",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    assert response.status_code == 200
    enqueue.assert_called_once_with(settings, "juninmd/repo#8")


def test_bot_issue_comment_does_not_dispatch(tmp_path):
    settings = _settings(tmp_path)
    settings.automation_mode = "autonomous"
    app = create_app(settings)
    body = (
        b'{"action":"created","issue":{"number":8,"pull_request":{"url":"pr"}},'
        b'"sender":{"type":"Bot"},"repository":{"full_name":"juninmd/repo"}}'
    )
    with patch("src.webhooks.server.enqueue_pr") as enqueue, TestClient(app) as client:
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Delivery": "delivery-bot-comment",
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": _signature(body),
            },
        )
    assert response.status_code == 200
    assert response.json()["pr_refs"] == []
    enqueue.assert_not_called()
