"""
Project Creator Agent - brainstorms ideas, creates repositories, and delegates
implementation to a Jules session.
"""

from __future__ import annotations

import json
import re
from typing import Any

from github import GithubException

from src.agents.base_agent import BaseAgent
from src.ai import get_ai_client

_AUTONOMOUS_NOTICE = (
    "| 🤖 Criado de forma autônoma pelo agente github-assistance. "
    "Autonomously created by the github-assistance AI agent."
)


class ProjectCreatorAgent(BaseAgent):
    """
    Project Creator Agent

    Reads instructions from instructions.md file.
    """

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        **kwargs,
    ):
        super().__init__(*args, name="project_creator", enforce_repository_allowlist=True, **kwargs)
        self._ai_client = get_ai_client(
            provider=ai_provider or "litellm", model=ai_model or "cloud/llama-70b", **(ai_config or {})
        )

    def run(self) -> dict[str, Any]:
        """Execute the Project Creator workflow."""
        self.log("Starting Project Creator workflow")

        try:
            idea_data = self.generate_project_idea()
            if not idea_data:
                return {"status": "failed", "reason": "could_not_generate_idea"}

            repo_name = idea_data.get("repository_name")
            repo_title = idea_data.get("title") or repo_name
            project_idea = idea_data.get("idea_description")
            tech_stack = idea_data.get("tech_stack", "")
            jules_prompt = idea_data.get("jules_prompt", "")

            if not repo_name or not project_idea or not jules_prompt:
                return {"status": "failed", "reason": "invalid_idea_format"}

            repo_name = re.sub(r"[^a-z0-9-]", "-", repo_name.lower())
            repo_name = re.sub(r"-+", "-", repo_name).strip("-")
            full_repo_name = f"{self.target_owner}/{repo_name}"

            self._notify_idea(repo_name, project_idea, tech_stack)

            instructions = self.load_jules_instructions(
                variables={
                    "repository_name": full_repo_name,
                    "project_title": repo_title,
                    "project_idea": project_idea,
                    "tech_stack": tech_stack,
                    "jules_prompt": jules_prompt,
                }
            )

            repo = self._create_github_repo(repo_name, project_idea)
            if not repo:
                return {"status": "failed", "reason": "repo_creation_failed"}

            if not self._ensure_master_branch(repo):
                return {"status": "failed", "reason": "master_branch_failed"}

            self.allowlist.add_repository(full_repo_name)
            session = self.create_jules_session(
                repository=full_repo_name,
                instructions=instructions,
                title=f"Initial implementation for {repo_title}",
                base_branch="master",
            )
            repo_url = f"https://github.com/{full_repo_name}"
            self._notify_created(full_repo_name, project_idea, None, repo_url)
            return {
                "status": "session_created",
                "repository": full_repo_name,
                "idea": project_idea,
                "session_id": session.get("id"),
                "repo_url": repo_url,
            }

        except Exception as e:
            self.log(f"Project Creator failed: {e}", "ERROR")
            self._notify_failed(str(e))
            return {"status": "failed"}

    def _safe_send(self, text: str, log_label: str, **kwargs) -> None:
        if not self.telegram:
            return
        try:
            self.telegram.send_message(text, parse_mode="HTML", **kwargs)
        except Exception as exc:
            self.log(f"Failed to send {log_label} notification: {exc}", "WARNING")

    def _notify_idea(self, repo_name: str, idea: str, tech_stack: str = "") -> None:
        esc = self.telegram.escape_html if self.telegram else str
        lines = [
            "💡 <b>NOVA IDEIA DE PROJETO</b>",
            "──────────────────────",
            f"📦 <b>Repositório:</b> <code>{esc(repo_name)}</code>",
        ]
        if tech_stack:
            lines.append(f"🛠 <b>Stack:</b> <code>{esc(tech_stack)}</code>")
        lines += [
            "📝 <b>Descrição:</b>",
            f"<i>{esc(idea)}</i>",
            "──────────────────────",
            "⚙️ Abrindo sessão no Jules…",
        ]
        self._safe_send("\n".join(lines), "idea")

    def _notify_created(
        self,
        full_repo_name: str,
        idea: str,
        session_id: str | None = None,
        repo_url: str | None = None,
    ) -> None:
        esc = self.telegram.escape_html if self.telegram else str
        url = repo_url or f"https://github.com/{full_repo_name}"
        text = (
            f"✅ <b>PROJETO CRIADO COM SUCESSO</b>\n"
            f"──────────────────────\n"
            f"📦 <b>Repositório:</b> <code>{esc(full_repo_name)}</code>\n"
            f"📝 <b>Ideia:</b> <i>{esc(idea[:250])}</i>\n"
        )
        if session_id:
            text += f"⚙️ <b>Jules Sessão:</b> <code>{esc(session_id)}</code>\n"
        text += (
            f"──────────────────────\n"
            f'🔗 <a href="{url}">Abrir no GitHub</a>'
        )
        reply_markup = {"inline_keyboard": [[{"text": "🔗 Ver repositório", "url": url}]]}
        self._safe_send(text, "created", reply_markup=reply_markup)

    def _notify_failed(self, error: str = "Unknown error") -> None:
        text = (
            f"❌ <b>PROJECT CREATOR — FALHA</b>\n"
            f"──────────────────────\n"
            f"<pre>{self.telegram.escape_html(error[:300]) if self.telegram else error[:300]}</pre>"
        )
        self._safe_send(text, "failure")

    def _create_github_repo(self, repo_name: str, project_idea: str) -> Any | None:
        """Create a private GitHub repository for autonomous implementation."""
        description = f"{project_idea[:250]} {_AUTONOMOUS_NOTICE}"[:350]
        authenticated_user = self.github_client.g.get_user()
        try:
            repo = authenticated_user.create_repo(  # type: ignore[attr-defined]
                name=repo_name,
                description=description,
                private=True,
                auto_init=True,
            )
            self.log(f"Created repository: {self.target_owner}/{repo_name}")
            return repo
        except GithubException as e:
            self.log(f"Failed to create repository: {e.status} {e.data}", "ERROR")
            return None
        except Exception as e:
            self.log(f"Unexpected error creating repository: {e}", "ERROR")
            return None

    def _ensure_master_branch(self, repo: Any) -> bool:
        """Ensure Jules starts from master, regardless of the account default branch."""
        try:
            default_branch = getattr(repo, "default_branch", "master")
            if default_branch != "master":
                default_ref = repo.get_git_ref(f"heads/{default_branch}")
                repo.create_git_ref("refs/heads/master", default_ref.object.sha)
                repo.edit(default_branch="master")
            return True
        except GithubException as e:
            if e.status == 422:
                try:
                    repo.edit(default_branch="master")
                    return True
                except Exception as edit_error:
                    self.log(f"Failed to set master as default branch: {edit_error}", "ERROR")
                    return False
            self.log(f"Failed to ensure master branch: {e.status} {e.data}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Unexpected error ensuring master branch: {e}", "ERROR")
            return False

    def _fetch_existing_repos(self) -> list[str]:
        """Fetch list of existing repository names for context."""
        try:
            repos = self.github_client.get_user_repos(sort="updated", limit=20)
            return [r.name for r in repos]
        except Exception as e:
            self.log(f"Failed to fetch existing repos: {e}", "WARNING")
            return []

    def generate_project_idea(self) -> dict[str, Any] | None:
        """Use AI to brainstorm a personalized new project idea."""
        if not self._ai_client:
            self.log("AI client is not configured.", "ERROR")
            return None

        existing_repos = self._fetch_existing_repos()
        repos_list = ", ".join(existing_repos) if existing_repos else "none yet"

        prompt = (
            "You are a senior software engineer and entrepreneur helping a Brazilian developer (Antonio Carlos) "
            "decide what to build next.\n\n"
            f"His existing GitHub repositories (most recently updated): {repos_list}\n\n"
            "Based on the portfolio above:\n"
            "- Identify a gap or complementary tool that would genuinely be useful\n"
            "- Favor: CLI tools, automation bots, developer productivity, AI integrations, "
            "personal finance helpers, health/fitness trackers, or fun Brazilian-culture apps\n"
            "- Avoid duplicating existing repos\n"
            "- The project must be completable as a working MVP in a single session\n\n"
            "Brainstorm ONE unique project idea.\n\n"
            "Respond EXACTLY with the following JSON format and nothing else:\n"
            "{\n"
            '  "repository_name": "a-short-kebab-case-name",\n'
            '  "title": "A short human-friendly project title",\n'
            '  "idea_description": "A detailed 2-3 sentence description: what it does, who uses it, and why it is useful or fun.",\n'
            '  "tech_stack": "e.g. Python + FastAPI, or Node.js + TypeScript, or Go CLI",\n'
            '  "jules_prompt": "A complete implementation prompt for Jules. Tell Jules to build all code on master, include tests, docs, validation commands, and open a PR when done."\n'
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
