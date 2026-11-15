import pytest


@pytest.fixture(autouse=True)
def _disable_llm_cache(monkeypatch):
    """Keep tests isolated: identical prompts across tests must not share cached answers."""
    monkeypatch.setenv("AI_CACHE", "0")


@pytest.fixture(autouse=True)
def _disable_gitleaks_by_default(monkeypatch):
    """gitleaks may or may not be installed on the dev machine; tests opt in explicitly."""
    monkeypatch.setenv("PUSH_GUARD_GITLEAKS", "off")


@pytest.fixture(autouse=True)
def _disable_sast_by_default(monkeypatch):
    """trufflehog/trivy/semgrep may be installed locally; tests opt in explicitly."""
    monkeypatch.setenv("PUSH_GUARD_SAST", "off")
