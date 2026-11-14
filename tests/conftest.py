import pytest


@pytest.fixture(autouse=True)
def _disable_llm_cache(monkeypatch):
    """Keep tests isolated: identical prompts across tests must not share cached answers."""
    monkeypatch.setenv("AI_CACHE", "0")
