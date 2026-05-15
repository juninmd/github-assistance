"""
Utility functions for agents.
"""
from pathlib import Path
from typing import Any
from datetime import UTC, datetime, timedelta


def load_instructions(agent_name: str, log_func: Any = None) -> str:
    """Load agent instructions from markdown file."""
    agent_dir = Path(__file__).parent / agent_name
    instructions_file = agent_dir / 'instructions.md'

    if not instructions_file.exists():
        if log_func:
            log_func(f"Instructions file not found: {instructions_file}", "WARNING")
        return ""

    try:
        with open(instructions_file, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        if log_func:
            log_func(f"Error loading instructions: {e}", "ERROR")
        return ""


def load_jules_instructions(
    agent_name: str,
    template_name: str = "jules-instructions.md",
    variables: dict[str, Any] | None = None,
    log_func: Any = None,
) -> str:
    """Load Jules task instructions from markdown template and replace variables."""
    agent_dir = Path(__file__).parent / agent_name
    template_file = agent_dir / template_name

    if not template_file.exists():
        if log_func:
            log_func(f"Jules instructions template not found: {template_file}", "ERROR")
        return ""

    try:
        with open(template_file, encoding='utf-8') as f:
            template = f.read()

        if variables:
            for key, value in variables.items():
                placeholder = f"{{{{{key}}}}}"
                template = template.replace(placeholder, str(value))

        return template

    except Exception as e:
        if log_func:
            log_func(f"Error loading Jules instructions: {e}", "ERROR")
        return ""


def get_instructions_section(instructions: str, section_header: str) -> str:
    """Extract a specific section from instructions markdown."""
    if not instructions:
        return ""

    lines = instructions.split('\n')
    section_lines = []
    in_section = False
    header_level = 0

    for line in lines:
        if line.strip().startswith('#') and section_header.lower() in line.lower():
            in_section = True
            header_level = len(line.split()[0])
            continue

        if in_section:
            if line.strip().startswith('#'):
                current_level = len(line.split()[0])
                if current_level <= header_level:
                    break
            section_lines.append(line)

    return '\n'.join(section_lines).strip()


def check_github_rate_limit(github_client: Any, log_func: Any = None) -> int:
    """Check GitHub API rate limit and log a warning if running low."""
    try:
        rate_limit = github_client.g.get_rate_limit()
        remaining = rate_limit.rate.remaining
        limit = rate_limit.rate.limit
        pct = (remaining / limit * 100) if limit else 0

        if log_func:
            if pct < 10:
                log_func(f"⚠️ GitHub API rate limit critical: {remaining}/{limit} ({pct:.0f}%)", "WARNING")
            elif pct < 25:
                log_func(f"GitHub API rate limit low: {remaining}/{limit} ({pct:.0f}%)", "WARNING")

        return remaining
    except Exception as e:
        if log_func:
            log_func(f"Could not check rate limit: {e}", "WARNING")
        return -1


def has_recent_jules_session(
    jules_client: Any,
    repository: str,
    task_keyword: str = "",
    hours: int = 24,
    log_func: Any = None,
    cached_sessions: list[dict] | None = None,
) -> bool:
    """Check if a Jules session was already created recently for this repo/task."""
    try:
        sessions = cached_sessions if cached_sessions is not None else jules_client.list_sessions(page_size=100)
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        for session in sessions:
            created_at = session.get("createTime") or session.get("createdAt")
            if not created_at:
                continue
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

            title = (session.get("title") or "").lower()
            repo_match = repository.lower() in title
            task_match = not task_keyword or task_keyword.lower() in title

            if repo_match and task_match:
                if log_func:
                    log_func(f"Skipping duplicate: recent session found for {repository} ({task_keyword})")
                return True
        return False
    except Exception as e:
        if log_func:
            log_func(f"Could not check recent sessions: {e}", "WARNING")
        return False
