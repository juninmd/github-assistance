import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

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
