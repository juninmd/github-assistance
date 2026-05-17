"""AI-powered analysis of gitleaks findings for the Secret Remover Agent."""
from typing import Any

from src.ai import AIClient


def analyze_finding(finding: dict[str, Any], ai_client: AIClient) -> dict[str, Any]:
    """Ask the AI to classify one gitleaks finding.

    Returns a dict with keys 'action' (REMOVE_FROM_HISTORY | IGNORE) and 'reason'.
    Falls back to IGNORE on any error to avoid destructive mistakes.
    """
    return ai_client.classify_secret_finding(
        finding=finding,
        redacted_context=str(finding.get("redacted_context", "")),
    )
