"""
Jules API Client for integrating with Google's Jules development assistant.
API Reference: https://jules.google/docs/api/reference/
"""
import os
import requests
from typing import Optional, Dict, Any, List
import time


class JulesClient:
    """
    Client for interacting with the Jules v1alpha REST API.

    The Jules API uses sessions (not tasks). A session is a continuous unit
    of work within a specific source context (e.g., a GitHub repository).

    Authentication is via X-Goog-Api-Key header.
    """

    BASE_URL = "https://jules.googleapis.com"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Jules API client.

        Args:
            api_key: Jules API key. If not provided, reads from JULES_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("JULES_API_KEY")
        
        # We allow initialization without key, but methods might fail
        if not self.api_key:
            # print("Warning: Jules API key is missing. Jules features will not work.")
            pass

        self.headers = {
            "X-Goog-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def list_sources(self) -> List[Dict[str, Any]]:
        """
        List all connected sources (GitHub repositories).

        Returns:
            List of source objects with name, id, and githubRepo info.
        """
        sources = []
        page_token = None

        while True:
            params = {}
            if page_token:
                params["pageToken"] = page_token

            response = requests.get(
                f"{self.BASE_URL}/v1alpha/sources",
                headers=self.headers,
                params=params,
                timeout=30
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

    def create_session(
        self,
        source: str,
        prompt: str,
        title: Optional[str] = None,
        starting_branch: str = "main",
        automation_mode: str = "AUTO_CREATE_PR",
        require_plan_approval: bool = False
    ) -> Dict[str, Any]:
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
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {
                    "startingBranch": starting_branch
                }
            }
        }

        if title:
            payload["title"] = title
        if automation_mode:
            payload["automationMode"] = automation_mode
        if require_plan_approval:
            payload["requirePlanApproval"] = True

        response = requests.post(
            f"{self.BASE_URL}/v1alpha/sessions",
            headers=self.headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        return response.json()

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get the details of a Jules session.

        Args:
            session_id: The session identifier.

        Returns:
            Session object with current status, outputs, etc.
        """
        response = requests.get(
            f"{self.BASE_URL}/v1alpha/sessions/{session_id}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def list_sessions(self, page_size: int = 20) -> List[Dict[str, Any]]:
        """
        List sessions.

        Args:
            page_size: Number of sessions to return per page.

        Returns:
            List of session objects.
        """
        response = requests.get(
            f"{self.BASE_URL}/v1alpha/sessions",
            headers=self.headers,
            params={"pageSize": page_size},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("sessions", [])

    def approve_plan(self, session_id: str) -> Dict[str, Any]:
        """
        Approve the latest plan for a session that requires plan approval.

        Args:
            session_id: The session identifier.

        Returns:
            Response from the API.
        """
        response = requests.post(
            f"{self.BASE_URL}/v1alpha/sessions/{session_id}:approvePlan",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def send_message(self, session_id: str, prompt: str) -> Dict[str, Any]:
        """
        Send a follow-up message to the agent within a session.

        Args:
            session_id: The session identifier.
            prompt: The message text.

        Returns:
            Response from the API (may be empty; check activities for reply).
        """
        response = requests.post(
            f"{self.BASE_URL}/v1alpha/sessions/{session_id}:sendMessage",
            headers=self.headers,
            json={"prompt": prompt},
            timeout=30
        )
        response.raise_for_status()
        return response.json() if response.text else {}

    def list_activities(
        self,
        session_id: str,
        page_size: int = 30
    ) -> List[Dict[str, Any]]:
        """
        List activities within a session.

        Args:
            session_id: The session identifier.
            page_size: Number of activities to return per page.

        Returns:
            List of activity objects.
        """
        response = requests.get(
            f"{self.BASE_URL}/v1alpha/sessions/{session_id}/activities",
            headers=self.headers,
            params={"pageSize": page_size},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("activities", [])

    def wait_for_session(
        self,
        session_id: str,
        max_wait_seconds: int = 3600,
        poll_interval: int = 30
    ) -> Dict[str, Any]:
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
        )

    def create_pull_request_session(
        self,
        repository: str,
        prompt: str,
        title: Optional[str] = None,
        base_branch: str = "main"
    ) -> Dict[str, Any]:
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
        source = self.get_source_name(repository)

        return self.create_session(
            source=source,
            prompt=prompt,
            title=title,
            starting_branch=base_branch,
            automation_mode="AUTO_CREATE_PR"
        )
