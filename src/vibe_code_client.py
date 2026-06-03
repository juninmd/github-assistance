"""Small HTTP client for creating Vibe-Code tasks."""

from __future__ import annotations

import os
from typing import Any

import requests


class VibeCodeClient:
    """Creates repository-backed tasks in a local or remote Vibe-Code server."""

    def __init__(
        self,
        base_url: str | None = None,
        workspace_id: str | None = None,
        api_key: str | None = None,
        timeout: int = 30,
    ):
        raw_url = base_url or os.getenv("VIBE_CODE_API_URL") or "http://localhost:3000/api"
        self.base_url = raw_url.rstrip("/")
        if not self.base_url.endswith("/api"):
            self.base_url = f"{self.base_url}/api"
        self.workspace_id = workspace_id or os.getenv("VIBE_CODE_WORKSPACE_ID")
        self.api_key = api_key or os.getenv("VIBE_CODE_API_KEY") or os.getenv("VIBE_CODE_TOKEN")
        self.timeout = timeout

    def create_opencode_task(
        self,
        repository: str,
        instructions: str,
        title: str,
        base_branch: str | None = None,
    ) -> dict[str, Any]:
        repo = self._ensure_repo(repository)
        payload: dict[str, Any] = {
            "title": title,
            "description": instructions,
            "repoId": repo["id"],
            "engine": "opencode",
            "tags": ["github-assistance", "opencode"],
        }
        if base_branch:
            payload["baseBranch"] = base_branch

        response = self._request("POST", "/tasks", json=payload)
        task = response.get("data", response)
        return {
            "status": "task_created",
            "task_id": task.get("id"),
            "task_url": self._task_url(task.get("id")),
            "repository": repository,
            "engine": task.get("engine", "opencode"),
        }

    def _ensure_repo(self, repository: str) -> dict[str, Any]:
        repo_url = self._repo_url(repository)
        for repo in self._request("GET", "/repos").get("data", []):
            if repo.get("url") == repo_url:
                return repo

        response = self._request("POST", "/repos", json={"url": repo_url})
        return response.get("data", response)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        if self.workspace_id:
            headers["x-workspace-id"] = self.workspace_id
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=self.timeout,
            **kwargs,
        )
        if response.status_code == 409 and method == "POST" and path == "/repos":
            return {"data": self._find_repo(kwargs["json"]["url"])}
        response.raise_for_status()
        return response.json()

    def _find_repo(self, repo_url: str) -> dict[str, Any]:
        for repo in self._request("GET", "/repos").get("data", []):
            if repo.get("url") == repo_url:
                return repo
        raise RuntimeError(f"Vibe-Code repository exists but was not returned: {repo_url}")

    def _task_url(self, task_id: str | None) -> str | None:
        if not task_id:
            return None
        app_url = self.base_url.removesuffix("/api")
        return f"{app_url}/tasks/{task_id}"

    @staticmethod
    def _repo_url(repository: str) -> str:
        if repository.startswith(("http://", "https://")):
            return repository
        return f"https://github.com/{repository}.git"
