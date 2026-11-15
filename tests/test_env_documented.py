"""Drift guard: every env var read in src/ must be documented in .env.example."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Standard/ambient variables that are not project configuration.
IGNORED = {"GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "telegram_bot_token", "telegram_chat_id",
           "AI_CACHE", "HOME", "PATH"}


def test_every_env_read_is_documented():
    used = set()
    for py in (ROOT / "src").rglob("*.py"):
        used |= set(re.findall(r"(?:environ\.get|getenv)\(\s*[\"']([A-Za-z_0-9]+)", py.read_text()))
    documented = set(re.findall(r"^#?\s*([A-Za-z_0-9]+)=", (ROOT / ".env.example").read_text(), re.M))
    missing = sorted(used - documented - IGNORED)
    assert not missing, f"document in .env.example: {missing}"
