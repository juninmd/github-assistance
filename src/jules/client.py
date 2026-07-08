"""
Jules API Client for integrating with Google's Jules development assistant.
API Reference: https://jules.google/docs/api/reference/
"""

import os
import time
import warnings
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from src.utils.retry import with_retry

_JULES_RETRYABLE = {429, 500, 502, 503, 504}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


_JULES_TIMEOUT = _env_int("JULES_TIMEOUT_SECONDS", 300)
_JULES_WAIT_SECONDS = _env_int("JULES_WAIT_SECONDS", 14400)
_JULES_RETRY_ATTEMPTS = _env_int("JULES_RETRY_ATTEMPTS", 3)


def _is_jules_retryable(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        return getattr(exc.response, "status_code", None) in _JULES_RETRYABLE
    return isinstance(exc, (requests.ConnectionError, requests.Timeout))


def _is_jules_create_retryable(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        return getattr(exc.response, "status_code", None) == 429
    return False


class JulesClient:
    """
    Client for interacting with the Jules v1alpha REST API.

    The Jules API uses sessions (not tasks). A session is a continuous unit
    of work within a specific source context (e.g., a GitHub repository).

    Authentication is via X-Goog-Api-Key header.
    """

    BASE_URL = "https://jules.googleapis.com"

    def __init__(self, api_key: str | None = None):
        """
        Initialize Jules API client.

        Args:
            api_key: Jules API key. If not provided, reads from JULES_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("JULES_API_KEY")

        if not self.api_key:
            warnings.warn(
                "Jules API key is missing (JULES_API_KEY). Jules features will not work.",
                stacklevel=2,
            )

        self.headers = {"X-Goog-Api-Key": self.api_key, "Content-Type": "application/json"}

    @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=2.0, retryable=_is_jules_retryable)
    def list_sources(self) -> list[dict[str, Any]]:
        sources = []
        page_token = None

        while True:
            params = {"pageToken": page_token} if page_token else {}
            response = requests.get(
                f"{self.BASE_URL}/v1alpha/sources", headers=self.headers, params=params, timeout=_JULES_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            sources.extend(data.get("sources", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return sources

    def get_source_name(self, repository: str) -> str:
        """
        Convert a repository identifier (e.g., 'owner/repo') into a Jules
        source name (e.g., 'sources/github/owner/repo').

        Args:
            repository: Repository in 'owner/repo' format.

        Returns:
            Jules source name string.
        """
        return f"sources/github/{repository}"

    def _normalize_session_id(self, session_id: str) -> str:
        """Accept raw ids and full resource names returned by the API."""
        prefix = "sessions/"
        if session_id.startswith(prefix):
            return session_id[len(prefix) :]
        return session_id

    def create_session(
        self,
        source: str,
        prompt: str,
        title: str | None = None,
        starting_branch: str | None = None,
        automation_mode: str = "AUTO_CREATE_PR",
        require_plan_approval: bool = True,
    ) -> dict[str, Any]:
        """
        Create a new Jules session.

        Args:
            source: Source name (e.g., 'sources/github/owner/repo').
            prompt: Natural language instructions for Jules.
            title: Optional session title.
            starting_branch: Branch to work from (default: 'main').
            automation_mode: Automation mode. 'AUTO_CREATE_PR' will auto-create
                             a PR when work is done.
            require_plan_approval: If True, the session will pause for plan
                                   approval before proceeding.

        Returns:
            Session object with id, name, title, etc.
        """
        if not starting_branch:
            raise ValueError("starting_branch is required and must be provided")

        payload: dict[str, Any] = {
            "prompt": prompt,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {"startingBranch": starting_branch},
            },
        }

        if title:
            payload["title"] = title
        if automation_mode:
            payload["automationMode"] = automation_mode
        payload["requirePlanApproval"] = require_plan_approval

        started_at = datetime.now(UTC) - timedelta(seconds=30)

        @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=2.0, retryable=_is_jules_create_retryable)
        def _post() -> dict[str, Any]:
            resp = requests.post(
                f"{self.BASE_URL}/v1alpha/sessions",
                headers=self.headers,
                json=payload,
                timeout=_JULES_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            return _post()
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status and 400 <= status < 500:
                recovered = self._reconcile_created_session(
                    title=title,
                    prompt=prompt,
                    source=source,
                    started_at=started_at,
                )
                if recovered:
                    return recovered
            raise

    @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=1.0, retryable=_is_jules_retryable)
    def get_session(self, session_id: str) -> dict[str, Any]:
        """
        Get the details of a Jules session.

        Args:
            session_id: The session identifier.

        Returns:
            Session object with current status, outputs, etc.
        """
        normalized_session_id = self._normalize_session_id(session_id)
        response = requests.get(
            f"{self.BASE_URL}/v1alpha/sessions/{normalized_session_id}",
            headers=self.headers,
            timeout=_JULES_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=1.0, retryable=_is_jules_retryable)
    def list_sessions(
        self,
        page_size: int = 50,
        max_pages: int | None = None,
        timeout: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List all sessions, paginating automatically.

        Args:
            page_size: Number of sessions to return per page.
            max_pages: Maximum pages to fetch (None = all).

        Returns:
            List of all session objects across all pages.
        """
        sessions: list[dict[str, Any]] = []
        page_token: str | None = None
        pages_fetched = 0

        while True:
            params: dict[str, Any] = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(
                f"{self.BASE_URL}/v1alpha/sessions",
                headers=self.headers,
                params=params,
                timeout=timeout or _JULES_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            sessions.extend(data.get("sessions", []))
            pages_fetched += 1
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            if max_pages is not None and pages_fetched >= max_pages:
                break

        return sessions

    def _reconcile_created_session(
        self,
        title: str | None,
        prompt: str,
        source: str | None,
        started_at: datetime,
    ) -> dict[str, Any] | None:
        """Recover a session when Jules returns an ambiguous 4xx after creation."""
        try:
            sessions = self.list_sessions(page_size=100, max_pages=3, timeout=10)
        except Exception:
            return None

        for session in sessions:
            created_at = self._parse_create_time(session.get("createTime"))
            if created_at and created_at < started_at:
                continue
            if title and session.get("title") != title:
                continue
            if not title and session.get("prompt") != prompt:
                continue
            if source and session.get("sourceContext", {}).get("source") != source:
                continue
            return session
        return None

    def _parse_create_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=1.0, retryable=_is_jules_retryable)
    def approve_plan(self, session_id: str) -> dict[str, Any]:
        """
        Approve the latest plan for a session that requires plan approval.

        Args:
            session_id: The session identifier.

        Returns:
            Response from the API.
        """
        normalized_session_id = self._normalize_session_id(session_id)
        response = requests.post(
            f"{self.BASE_URL}/v1alpha/sessions/{normalized_session_id}:approvePlan",
            headers=self.headers,
            timeout=_JULES_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=1.0, retryable=_is_jules_retryable)
    def send_message(self, session_id: str, prompt: str) -> dict[str, Any]:
        """
        Send a follow-up message to the agent within a session.

        Args:
            session_id: The session identifier.
            prompt: The message text.

        Returns:
            Response from the API (may be empty; check activities for reply).
        """
        normalized_session_id = self._normalize_session_id(session_id)
        response = requests.post(
            f"{self.BASE_URL}/v1alpha/sessions/{normalized_session_id}:sendMessage",
            headers=self.headers,
            json={"prompt": prompt},
            timeout=_JULES_TIMEOUT,
        )
        response.raise_for_status()
        return response.json() if response.text else {}

    @with_retry(max_attempts=_JULES_RETRY_ATTEMPTS, base_delay=1.0, retryable=_is_jules_retryable)
    def list_activities(self, session_id: str, page_size: int = 100) -> list[dict[str, Any]]:
        """
        List all activities within a session, paginating automatically.

        Args:
            session_id: The session identifier.
            page_size: Number of activities to return per page.

        Returns:
            List of all activity objects across all pages.
        """
        normalized_session_id = self._normalize_session_id(session_id)
        activities: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(
                f"{self.BASE_URL}/v1alpha/sessions/{normalized_session_id}/activities",
                headers=self.headers,
                params=params,
                timeout=_JULES_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            activities.extend(data.get("activities", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return activities

    def wait_for_session(
        self, session_id: str, max_wait_seconds: int = _JULES_WAIT_SECONDS, poll_interval: int = 30
    ) -> dict[str, Any]:
        """
        Wait for a session to produce outputs (e.g., a PR).

        Args:
            session_id: The session identifier.
            max_wait_seconds: Maximum time to wait in seconds.
            poll_interval: Time between status checks in seconds.

        Returns:
            Final session object.
        """
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            session = self.get_session(session_id)

            # Check if session has produced outputs (e.g., a pull request)
            outputs = session.get("outputs", [])
            if outputs:
                return session

            # Check for terminal states
            status = session.get("status", "")
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                return session

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Session {session_id} did not complete within {max_wait_seconds} seconds"
        )  # pragma: no cover

    def create_pull_request_session(
        self,
        repository: str,
        prompt: str,
        title: str | None = None,
        base_branch: str | None = None,
        require_plan_approval: bool = True,
    ) -> dict[str, Any]:
        """
        Convenience method: create a session that will auto-create a PR.

        Args:
            repository: Repository identifier (e.g., 'owner/repo').
            prompt: Detailed instructions for the work.
            title: Optional session title.
            base_branch: Base branch for the PR.

        Returns:
            Session object with id.
        """
        if not base_branch:
            raise ValueError("base_branch is required and must be provided")

        source = self.get_source_name(repository)

        return self.create_session(
            source=source,
            prompt=prompt,
            title=title,
            starting_branch=base_branch,
            automation_mode="AUTO_CREATE_PR",
            require_plan_approval=require_plan_approval,
        )
