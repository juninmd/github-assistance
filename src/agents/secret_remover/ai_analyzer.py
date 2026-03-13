"""AI-powered analysis of gitleaks findings for the Secret Remover Agent."""
import json
import re
from typing import Any

from src.ai_client import AIClient

_PROMPT = """\
You are a security expert reviewing a gitleaks finding from a Git repository.

Rule: {rule_id} - {description}
File: {file}
Line: {line}
Commit: {commit} ({date})

Decide whether this is a REAL SECRET or a FALSE POSITIVE:
- REMOVE_FROM_HISTORY: actual credentials, API tokens, private keys
- IGNORE: test/fake data, already-revoked tokens, documentation examples

Respond with ONLY valid JSON (no markdown fences):
{{"action": "REMOVE_FROM_HISTORY", "reason": "brief explanation"}}
or
{{"action": "IGNORE", "reason": "brief explanation"}}
"""


def analyze_finding(finding: dict[str, Any], ai_client: AIClient) -> dict[str, Any]:
    """Ask the AI to classify one gitleaks finding.

    Returns a dict with keys 'action' (REMOVE_FROM_HISTORY | IGNORE) and 'reason'.
    Falls back to IGNORE on any error to avoid destructive mistakes.
    """
    prompt = _PROMPT.format(
        rule_id=finding.get("rule_id", "unknown"),
        description=finding.get("description", ""),
        file=finding.get("file", ""),
        line=finding.get("line", 0),
        commit=finding.get("commit", ""),
        date=finding.get("date", ""),
    )
    try:
        raw = ai_client.generate(prompt)
        return _parse_ai_response(raw)
    except Exception as exc:
        return {"action": "IGNORE", "reason": f"AI analysis failed: {exc}"}


def _parse_ai_response(raw: str) -> dict[str, Any]:
    """Extract JSON from raw AI text, stripping optional markdown code fences."""
    cleaned = re.sub(r"```[a-z]*\s*", "", raw).strip().strip("`").strip()
    try:
        data = json.loads(cleaned)
        if data.get("action") in ("REMOVE_FROM_HISTORY", "IGNORE"):
            return {"action": data["action"], "reason": data.get("reason", "")}
    except (json.JSONDecodeError, AttributeError):
        pass
    return {"action": "IGNORE", "reason": "Could not parse AI response"}
