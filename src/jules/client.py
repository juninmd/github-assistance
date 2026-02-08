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
    Client for interacting with Jules API to automate development tasks.
    """

    BASE_URL = "https://api.jules.google"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Jules API client.

        Args:
            api_key: Jules API key. If not provided, reads from JULES_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("JULES_API_KEY")
        if not self.api_key:
            raise ValueError("Jules API key is required. Set JULES_API_KEY environment variable.")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def create_task(
        self,
        repository: str,
        branch: str,
        instructions: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new development task in Jules.

        Args:
            repository: Repository URL or identifier (e.g., "owner/repo")
            branch: Branch name to work on
            instructions: Detailed instructions for Jules
            title: Optional title for the task
            description: Optional description
            context: Optional additional context

        Returns:
            Task creation response with task_id
        """
        payload = {
            "repository": repository,
            "branch": branch,
            "instructions": instructions,
        }

        if title:
            payload["title"] = title
        if description:
            payload["description"] = description
        if context:
            payload["context"] = context

        response = requests.post(
            f"{self.BASE_URL}/v1/tasks",
            headers=self.headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a Jules task.

        Args:
            task_id: The task identifier

        Returns:
            Task status information
        """
        response = requests.get(
            f"{self.BASE_URL}/v1/tasks/{task_id}",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def wait_for_task_completion(
        self,
        task_id: str,
        max_wait_seconds: int = 3600,
        poll_interval: int = 30
    ) -> Dict[str, Any]:
        """
        Wait for a task to complete.

        Args:
            task_id: The task identifier
            max_wait_seconds: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds

        Returns:
            Final task status
        """
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            status = self.get_task_status(task_id)

            if status.get("status") in ["completed", "failed", "cancelled"]:
                return status

            time.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete within {max_wait_seconds} seconds")

    def create_pull_request_task(
        self,
        repository: str,
        feature_description: str,
        base_branch: str = "main",
        agent_persona: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a task that will result in a Pull Request.

        Args:
            repository: Repository identifier
            feature_description: Description of the feature to implement
            base_branch: Base branch for the PR
            agent_persona: Optional persona context for Jules

        Returns:
            Task information including task_id
        """
        instructions = f"""
        {f'Persona: {agent_persona}\n\n' if agent_persona else ''}
        Feature Request: {feature_description}

        Please:
        1. Create a new feature branch from {base_branch}
        2. Implement the requested feature
        3. Add appropriate tests
        4. Update documentation if needed
        5. Create a Pull Request with a clear description
        """

        return self.create_task(
            repository=repository,
            branch=f"feature/auto-{int(time.time())}",
            instructions=instructions,
            title=f"Feature: {feature_description[:50]}...",
            description=feature_description
        )

    def list_tasks(
        self,
        repository: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List tasks with optional filters.

        Args:
            repository: Filter by repository
            status: Filter by status (pending, running, completed, failed)
            limit: Maximum number of tasks to return

        Returns:
            List of tasks
        """
        params = {"limit": limit}
        if repository:
            params["repository"] = repository
        if status:
            params["status"] = status

        response = requests.get(
            f"{self.BASE_URL}/v1/tasks",
            headers=self.headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("tasks", [])

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """
        Cancel a running task.

        Args:
            task_id: The task identifier

        Returns:
            Cancellation confirmation
        """
        response = requests.post(
            f"{self.BASE_URL}/v1/tasks/{task_id}/cancel",
            headers=self.headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
