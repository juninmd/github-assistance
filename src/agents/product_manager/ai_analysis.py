"""AI-powered issue analysis used by the Product Manager agent."""
from typing import Any

from src.ai_client import AIClient


def analyze_issues_with_ai(ai_client: AIClient, issues: list, repo_description: str) -> dict[str, Any]:
    """
    Use AI to analyse open issues and produce strategic product insights.

    Args:
        ai_client: Any AIClient implementation (e.g. OllamaClient with llama3).
        issues: List of GitHub Issue objects (titles, labels, numbers).
        repo_description: Repository description string.

    Returns:
        Dict with keys:
            - ``ai_summary``     (str)       Two-sentence executive summary.
            - ``ai_priorities``  (list[str]) Up to 3 strategic priorities.
            - ``ai_highlights``  (list[str]) Specific issues the AI flagged as urgent.
    """
    if not issues:
        return {"ai_summary": "No open issues to analyse.", "ai_priorities": [], "ai_highlights": []}

    issue_list = "\n".join(
        f"#{i.number} [{', '.join(lb.name for lb in i.labels) or 'unlabeled'}] {i.title}"
        for i in issues[:40]
    )

    prompt = (
        "You are a seasoned Product Manager conducting a triage of a GitHub repository.\n"
        f"Repository context: {repo_description or 'No description available.'}\n\n"
        "Open issues (number, labels, title):\n"
        f"{issue_list}\n\n"
        "Respond in this exact format — no extra text:\n"
        "SUMMARY: <two sentences about overall product health and what demands most attention>\n"
        "PRIORITY: <first strategic priority>\n"
        "PRIORITY: <second strategic priority>\n"
        "PRIORITY: <third strategic priority>\n"
        "HIGHLIGHT: <issue number and title of the single most urgent item>\n"
        "HIGHLIGHT: <issue number and title of the second most urgent item>\n"
    )

    try:
        raw = ai_client.generate(prompt)
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        summary = next((ln[len("SUMMARY:"):].strip() for ln in lines if ln.startswith("SUMMARY:")), "")
        priorities = [ln[len("PRIORITY:"):].strip() for ln in lines if ln.startswith("PRIORITY:")][:3]
        highlights = [ln[len("HIGHLIGHT:"):].strip() for ln in lines if ln.startswith("HIGHLIGHT:")][:2]

        return {"ai_summary": summary, "ai_priorities": priorities, "ai_highlights": highlights}

    except Exception as exc:
        return {
            "ai_summary": f"AI analysis unavailable: {exc}",
            "ai_priorities": [],
            "ai_highlights": [],
        }
