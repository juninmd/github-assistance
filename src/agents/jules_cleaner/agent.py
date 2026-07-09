"""Delete old Jules sessions to keep the account clean."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


class JulesCleanerAgent(BaseAgent):
    """Remove Jules sessions older than the configured retention window."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, name="jules_cleaner", enforce_repository_allowlist=False, **kwargs)

    @property
    def persona(self) -> str:
        return "Jules retention operator"

    @property
    def mission(self) -> str:
        return "Delete Jules sessions older than the retention window."

    def run(self) -> dict[str, Any]:
        max_age_days = _env_int("JULES_CLEANER_MAX_AGE_DAYS", 3)
        page_size = _env_int("JULES_CLEANER_PAGE_SIZE", 100)
        timeout = _env_int("JULES_CLEANER_TIMEOUT_SECONDS", 90)
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        scanned = deleted = skipped_recent = skipped_unknown_age = failed = 0
        failed_sessions: list[str] = []

        self.log(f"Deleting Jules sessions created before {cutoff.isoformat()}")
        sessions = self.jules_client.list_sessions(page_size=page_size, timeout=timeout)

        for session in sessions:
            scanned += 1
            session_id = session.get("id") or session.get("name")
            created_at = self.jules_client._parse_create_time(session.get("createTime"))
            if not session_id or not created_at:
                skipped_unknown_age += 1
                continue
            if created_at >= cutoff:
                skipped_recent += 1
                continue

            try:
                self.jules_client.delete_session(session_id)
                deleted += 1
            except Exception as exc:
                failed += 1
                failed_sessions.append(str(session_id))
                self.log(f"Failed to delete Jules session {session_id}: {exc}", "ERROR")

        result = {
            "status": "failed" if failed else "success",
            "retention_days": max_age_days,
            "cutoff": cutoff.isoformat(),
            "scanned": scanned,
            "deleted": deleted,
            "skipped_recent": skipped_recent,
            "skipped_unknown_age": skipped_unknown_age,
            "failed": failed,
            "failed_sessions": failed_sessions[:20],
        }
        self.log(
            "Jules cleanup complete: "
            f"scanned={scanned} deleted={deleted} recent={skipped_recent} failed={failed}"
        )
        return result
