"""
Utility functions for agents.
"""
import os
import random
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


_OPENCODE_FREE_MODEL_CACHE: str | None = None
_OPENCODE_MODELS_TIMEOUT = int(os.getenv("OPENCODE_MODELS_TIMEOUT_SECONDS", "20"))
_OPENCODE_DEFAULT_FREE_MODEL = "opencode/big-pickle"


def _is_free_model(model: str) -> bool:
    return model.endswith("-free") or model == _OPENCODE_DEFAULT_FREE_MODEL


def get_random_free_opencode_model() -> str:
    global _OPENCODE_FREE_MODEL_CACHE
    if _OPENCODE_FREE_MODEL_CACHE is not None:
        return _OPENCODE_FREE_MODEL_CACHE
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True, text=True, timeout=_OPENCODE_MODELS_TIMEOUT,
        )
        if result.returncode != 0:
            _OPENCODE_FREE_MODEL_CACHE = _OPENCODE_DEFAULT_FREE_MODEL
            return _OPENCODE_FREE_MODEL_CACHE
        models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
        free = [m for m in models if _is_free_model(m)]
        if free:
            _OPENCODE_FREE_MODEL_CACHE = random.choice(free)
            return _OPENCODE_FREE_MODEL_CACHE
    except Exception:
        pass
    _OPENCODE_FREE_MODEL_CACHE = _OPENCODE_DEFAULT_FREE_MODEL
    return _OPENCODE_FREE_MODEL_CACHE


def build_pr_body(agent_name: str, title: str, opencode_output: str, model: str = "opencode") -> str:
    """Build a standardized PR body with automated origin metadata."""
    return (
        f"## 🤖 Alterações aplicadas automaticamente\n\n"
        f"### O que foi feito\n"
        f"{title}\n\n"
        f"### Saída do opencode\n"
        f"```\n{opencode_output[:1500]}\n```\n\n"
        f"---\n"
        f"🤖 **Origem Automatizada**\n"
        f"- **Agente:** `{agent_name}`\n"
        f"- **Modelo:** `{model}`\n"
        f"- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)"
    )


def load_instructions(agent_name: str, log_func: Callable[..., None] | None = None) -> str:
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
    log_func: Callable[..., None] | None = None,
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


_RATE_LIMIT_CACHE: dict[str, Any] = {"remaining": -1, "timestamp": 0.0}
_RATE_LIMIT_TTL = 300


def clear_rate_limit_cache() -> None:
    global _RATE_LIMIT_CACHE
    _RATE_LIMIT_CACHE = {"remaining": -1, "timestamp": 0.0}


def check_github_rate_limit(github_client: Any, log_func: Callable[..., None] | None = None) -> int:
    """Check GitHub API rate limit and log a warning if running low.

    Results are cached for 5 minutes to reduce API call consumption.
    """
    global _RATE_LIMIT_CACHE
    now = time.time()
    if now - _RATE_LIMIT_CACHE["timestamp"] < _RATE_LIMIT_TTL:
        return _RATE_LIMIT_CACHE["remaining"]
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

        _RATE_LIMIT_CACHE = {"remaining": remaining, "timestamp": now}
        return remaining
    except Exception as e:
        if log_func:
            log_func(f"Could not check rate limit: {e}", "WARNING")
        return -1


def extract_session_datetime(session: dict[str, Any]) -> datetime | None:
    """Extract datetime from a Jules session dictionary."""
    created_at = session.get("createTime") or session.get("createdAt")
    if not created_at:
        return None
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def is_same_day_utc_minus_3(session: dict[str, Any], target_date: Any | None) -> bool:
    """Check if a session was created on a specific date in UTC-3."""
    dt = extract_session_datetime(session)
    if dt is None:
        return False
    try:
        return (dt.astimezone(UTC) - timedelta(hours=3)).date() == target_date
    except Exception:
        return False


def has_recent_jules_session(
    jules_client: Any,
    repository: str,
    task_keyword: str = "",
    hours: int = 24,
    log_func: Callable[..., None] | None = None,
) -> bool:
    """Check if a Jules session was already created recently for this repo/task.

    Fetches up to 100 sessions (typically sorted by recency from the API)
    and checks for a match. Early-exits when sessions fall outside the
    cutoff window (assumes API returns most recent sessions first).
    """
    try:
        sessions = jules_client.list_sessions(page_size=100)
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        for session in sessions:
            dt = extract_session_datetime(session)
            if dt is None or dt < cutoff:
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
