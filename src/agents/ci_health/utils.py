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
    """Attempt to remediate a failing CI pipeline for a public repository."""
    if agent.has_recent_jules_session(repo.full_name, task_keyword="ci health"):
        agent.log(f"Skipping remediation for {repo.full_name}: recent Jules session exists")
        return None

    failures_text = "\n".join(
        [f"- {f['name']} ({f['conclusion']}): {f['url']}" for f in failures]
    )

    instructions = agent.load_jules_instructions(
        variables={
            "repository": repo.full_name,
            "failures": failures_text,
        }
    )

    try:
        session = agent.create_jules_session(
            repository=repo.full_name,
            instructions=instructions,
            title=f"Fix CI pipeline for {repo.full_name}",
            wait_for_completion=False,
        )
        return {
            "repository": repo.full_name,
            "session_id": session.get("id"),
            "session_name": session.get("name") or session.get("title"),
        }
    except Exception as exc:
        agent.log(f"Could not create Jules session for {repo.full_name}: {exc}", "WARNING")
        return create_issue_for_pipeline(agent, repo, failures_text)
