"""Utility functions for CI Health Agent."""
from typing import Any


def create_issue_for_pipeline(agent: Any, repo: Any, failures_text: str) -> dict[str, Any] | None:
    """Create a GitHub issue describing the CI failures."""
    ai_client = agent._get_ai_client()
    if ai_client:
        prompt = (
            f"Repository: {repo.full_name}\n"
            f"CI pipeline failures found in the last 24h:\n{failures_text}\n\n"
            "Write a concise GitHub issue body that explains the problem and suggests concrete steps to fix the workflow."
        )
        try:
            body = ai_client.generate(prompt).strip()
        except Exception as exc:
            agent.log(f"AI generation failed: {exc}", "WARNING")
            body = f"CI pipeline failures:\n{failures_text}"
    else:
        body = f"CI pipeline failures:\n{failures_text}"

    try:
        issue = repo.create_issue(
            title="CI pipeline failing - please fix",
            body=body,
        )
        return {"repository": repo.full_name, "issue_number": issue.number, "issue_url": issue.html_url}
    except Exception as exc:
        agent.log(f"Failed to create issue in {repo.full_name}: {exc}", "WARNING")
        return None

def remediate_pipeline(agent: Any, repo: Any, failures: list[dict[str, str]]) -> dict[str, Any] | None:
    """Attempt to remediate a failing CI pipeline for a public repository by creating an issue."""
    failures_text = "\n".join(
        [f"- {f['name']} ({f['conclusion']}): {f['url']}" for f in failures]
    )
    return create_issue_for_pipeline(agent, repo, failures_text)
