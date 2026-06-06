import hashlib
import hmac
from pathlib import Path

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
    body = b'{"action":"opened","repository":{"full_name":"juninmd/repo"}}'
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
