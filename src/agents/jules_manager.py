"""
Jules Session Manager - Handles creation and monitoring of Jules sessions.
"""
from collections.abc import Callable
from typing import Any

from src.jules.client import JulesClient


class JulesSessionManager:
    """Manages Jules sessions for agents."""

    def __init__(self, jules_client: JulesClient, log_func: Callable[[str, str], None]):
        self.client = jules_client
        self.log = log_func

    def create_session(
        self,
        repository: str,
        prompt: str,
        title: str,
        base_branch: str,
        wait_for_completion: bool = False,
    ) -> dict[str, Any]:
        """Create a Jules session and optionally wait for it."""
        self.log(f"Creating Jules session for {repository}: {title} on branch {base_branch}", "INFO")

        result = self.client.create_pull_request_session(
            repository=repository,
            prompt=prompt,
            title=title,
            base_branch=base_branch,
        )
        session_id = result.get("id")
        self.log(f"Created session {session_id}", "INFO")

        if wait_for_completion and session_id:
            self.log(f"Waiting for session {session_id} to complete...", "INFO")
            result = self.client.wait_for_session(session_id)
            self.log(f"Session {session_id} completed", "INFO")

        return result
