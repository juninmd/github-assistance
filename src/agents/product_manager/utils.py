"""
Utility functions for Product Manager Agent.
"""
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from github import GithubException
from github.Repository import Repository

from src.ai import AIClient


def is_roadmap_up_to_date(repo: Repository, log_func: Callable[..., None] | None = None) -> bool:
    """Check if ROADMAP.md was updated in the last 7 days."""
    try:
        commits = repo.get_commits(path="ROADMAP.md")
        latest = next(iter(commits), None)
        if not latest:
            return False  # No ROADMAP.md yet — should create one

        last_update = latest.commit.author.date.replace(tzinfo=UTC)
        age = datetime.now(UTC) - last_update
        if age < timedelta(days=7):
            if log_func:
                log_func(f"ROADMAP.md updated {age.days}d ago — still fresh")
            return True
    except GithubException:
        return False  # ROADMAP.md doesn't exist or error
    except Exception as e:
        if log_func:
            log_func(f"Error checking ROADMAP.md freshness: {e}", "WARNING")
    return False


def analyze_issues_with_ai_logic(
    ai_client: AIClient | None,
    issues: list[Any],
    repo_description: str,
    log_func: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Analyze issues using the configured AI client to extract summary and priorities."""
    if not ai_client or not issues:
        return {}

    issues_text = "\n".join(
        f"- [{issue.number}] {issue.title}: {', '.join(lb.name for lb in issue.labels)}"
        for issue in issues
    )

    prompt = (
        f"You are a Product Manager analyzing a repository.\n"
        f"Repository Description: {repo_description}\n"
        f"Here are the current open issues:\n{issues_text}\n\n"
        f"Analyze these issues and provide a brief strategic summary and a list of priorities. "
        f"Respond EXACTLY with the following JSON format and nothing else:\n"
        "{\n"
        '  "ai_summary": "A brief 2-sentence summary of the current state based on issues.",\n'
        '  "priorities": [\n'
        '    {"category": "Category Name (e.g., Bugs, Features, Tech Debt)", "count": 1, "urgency": "high"}\n'
        "  ]\n"
        "}"
    )

    try:
        response_text = ai_client.generate(prompt)
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        if log_func:
            log_func("Could not find JSON in AI response", "WARNING")
    except json.JSONDecodeError as e:
        if log_func:
            log_func(f"Failed to decode JSON from AI response: {e}", "WARNING")
    except Exception as e:
        if log_func:
            log_func(f"AI client failed to generate response: {e}", "WARNING")

    return {}


def analyze_repository(
    repository: str,
    repo_info: Repository,
    ai_client: AIClient | None,
    log_func: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Analyse repository state using GitHub data and AI-powered insights."""
    if log_func:
        log_func(f"Analyzing {repository}")

    # Get open issues and PRs
    issues = list(repo_info.get_issues(state='open'))[:50]  # Limit to 50

    # Label-based categorisation
    bugs = [i for i in issues if any(lb.name.lower() in ['bug', 'defect'] for lb in i.labels)]
    features = [i for i in issues if any(lb.name.lower() in ['feature', 'enhancement'] for lb in i.labels)]
    tech_debt = [i for i in issues if any(lb.name.lower() in ['tech-debt', 'refactor'] for lb in i.labels)]

    # AI-powered strategic analysis
    ai_result = analyze_issues_with_ai_logic(
        ai_client, issues, repo_info.description or "", log_func
    )

    return {
        "summary": ai_result.get("ai_summary") or f"Repository has {len(issues)} open issues",
        "priorities": ai_result.get("priorities") or [
            {"category": "Bugs", "count": len(bugs), "urgency": "high"},
            {"category": "Features", "count": len(features), "urgency": "medium"},
            {"category": "Technical Debt", "count": len(tech_debt), "urgency": "low"},
        ],
        "total_issues": len(issues),
        "repository_description": repo_info.description or "No description",
        "primary_language": repo_info.language or "Unknown",
    }


def generate_roadmap_instructions(
    analysis: dict[str, Any],
    load_jules_instructions_func: Callable[..., str],
    repository: str,
) -> str:
    """Build Jules task instructions enriched with AI-generated insights."""
    priorities_text = "\n".join(
        f"- {p['category']}: {p['count']} items (urgency: {p['urgency']})"
        for p in analysis.get("priorities", [])
    )
    return load_jules_instructions_func(
        variables={
            "repository": repository,
            "repository_description": analysis.get("repository_description", "No description"),
            "primary_language": analysis.get("primary_language", "Unknown"),
            "total_issues": analysis.get("total_issues", 0),
            "priorities": priorities_text,
        }
    )
