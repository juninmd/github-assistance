from unittest.mock import MagicMock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.webhooks import auth as auth_mod
from src.webhooks.auth import GitHubAppAuth


def test_app_jwt_uses_string_issuer(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(pem)

    token = GitHubAppAuth(3982807, 138493700, str(key_path)).jwt()
    payload = jwt.decode(token, key.public_key(), algorithms=["RS256"], options={"verify_aud": False})

    assert payload["iss"] == "3982807"


def test_installation_token_caches_and_refreshes(tmp_path, monkeypatch):
    key_path = tmp_path / "app.pem"
    key_path.write_text("dummy-key")
    auth = GitHubAppAuth(1, 2, str(key_path))
    monkeypatch.setattr(auth, "jwt", lambda: "fake-jwt")

    mock_post = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"token": "ghs_token123"}
    mock_post.return_value = mock_resp
    monkeypatch.setattr(auth_mod.requests, "post", mock_post)

    t1 = auth.installation_token()
    t2 = auth.installation_token()

    assert t1 == "ghs_token123"
    assert t2 == "ghs_token123"
    mock_post.assert_called_once()
