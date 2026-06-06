"""GitHub webhook and App authentication helpers."""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

import jwt
import requests

_API = "https://api.github.com"


def valid_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={digest}")


class GitHubAppAuth:
    def __init__(self, app_id: int, installation_id: int, private_key_path: str) -> None:
        self.app_id = app_id
        self.installation_id = installation_id
        self.private_key_path = Path(private_key_path)

    def jwt(self) -> str:
        now = int(time.time())
        key = self.private_key_path.read_text(encoding="utf-8")
        payload = {"iat": now - 60, "exp": now + 540, "iss": str(self.app_id)}
        return jwt.encode(payload, key, "RS256")

    def installation_token(self) -> str:
        response = requests.post(
            f"{_API}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {self.jwt()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        response.raise_for_status()
        return str(response.json()["token"])
