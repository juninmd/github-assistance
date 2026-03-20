"""
Project Creator Agent - Responsible for brainstorming ideas, creating GitHub repositories, and starting Jules sessions.
"""
import json
import re
from typing import Any

from github import GithubException

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client


class ProjectCreatorAgent(BaseAgent):
    """
    Project Creator Agent

    Reads instructions from instructions.md file.
    """

    @property
    def persona(self) -> str:
        """Load persona from instructions.md"""
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        """Load mission from instructions.md"""
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="project_creator", **kwargs)
        self._ai_client = get_ai_client(provider=ai_provider or "ollama", model=ai_model or "qwen3:1.7b", **(ai_config or {}))

    def run(self) -> dict[str, Any]:
        """Execute the Project Creator workflow."""
        self.log("Starting Project Creator workflow")

        try:
            # 1. Generate an idea
            idea_data = self.generate_project_idea()
            if not idea_data:
                return {"status": "failed", "reason": "could_not_generate_idea"}

            repo_name = idea_data.get("repository_name")
            project_idea = idea_data.get("idea_description")

            if not repo_name or not project_idea:
                return {"status": "failed", "reason": "invalid_idea_format"}

            # Format repository name to ensure it's valid (e.g. lowercase, hyphens)
            repo_name = re.sub(r'[^a-z0-9-]', '-', repo_name.lower())
            repo_name = re.sub(r'-+', '-', repo_name).strip('-')

            # 2. Check if repository already exists
            full_repo_name = f"{self.target_owner}/{repo_name}"
            repo_exists = True
            try:
                self.github_client.get_repo(full_repo_name)
                self.log(f"Repository {full_repo_name} already exists. Skipping creation.", "WARNING")
            except GithubException as e:
                if e.status == 404:
                    repo_exists = False
                else:
                    self.log(f"Error checking repository {full_repo_name}: {e}", "ERROR")
                    return {"status": "failed", "reason": f"error_checking_repo: {e}"}

            if repo_exists:
                return {"status": "skipped", "reason": "repository_already_exists", "repository": full_repo_name}

            # 3. Create repository
            self.log(f"Creating private repository: {full_repo_name}")
            user = self.github_client.g.get_user()

            try:
                repo = user.create_repo(
                    name=repo_name,
                    description=project_idea,
                    private=True,
                    auto_init=True,
                )
            except GithubException as e:
                self.log(f"Failed to create repository: {e.status} {e.data}", "ERROR")
                return {"status": "failed", "reason": f"repo_creation_failed: {e.data}"}
            except Exception as e:
                self.log(f"Unexpected error creating repository: {e}", "ERROR")
                return {"status": "failed", "reason": str(e)}

            # 4. Add to allowlist
            self.log(f"Adding {full_repo_name} to allowlist")
            self.allowlist.add_repository(full_repo_name)

            # 5. Create Jules Session
            instructions = self.load_jules_instructions(
                variables={
                    "repository_name": full_repo_name,
                    "project_idea": project_idea,
                }
            )

            # A default branch is created by auto_init=True. Usually "main".
            base_branch = getattr(repo, "default_branch", "main")

            session = self.create_jules_session(
                repository=full_repo_name,
                instructions=instructions,
                title=f"Initialise {repo_name} - AI Project",
                wait_for_completion=False,
                base_branch=base_branch,
            )

            return {
                "status": "success",
                "repository": full_repo_name,
                "idea": project_idea,
                "session_id": session.get("id"),
            }

        except Exception as e:
            self.log(f"Project Creator failed: {e}", "ERROR")
            return {"status": "failed", "error": str(e)}

    def generate_project_idea(self) -> dict[str, Any] | None:
        """Use AI to brainstorm a new project idea."""
        if not self._ai_client:
            self.log("AI client is not configured.", "ERROR")
            return None

        prompt = (
            "You are a visionary software engineer looking to build a new fun, exciting, and highly profitable "
            "project using Artificial Intelligence and the Jules AI development platform.\n"
            "Brainstorm ONE unique project idea.\n\n"
            "Respond EXACTLY with the following JSON format and nothing else:\n"
            "{\n"
            '  "repository_name": "a-short-kebab-case-name",\n'
            '  "idea_description": "A detailed 2-3 sentence description of the project, what it does, and how it makes money or is fun."\n'
            "}"
        )

        try:
            response_text = self._ai_client.generate(prompt)
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            self.log("Could not find JSON in AI response for project idea", "WARNING")
            return None
        except json.JSONDecodeError as e:  # pragma: no cover
            self.log(f"Failed to decode JSON from AI response: {e}", "WARNING")
            return None
        except Exception as e:
            self.log(f"AI client failed to generate idea: {e}", "ERROR")
            return None
