"""
Project Creator Agent - brainstorms ideas, creates repositories, and delegates
implementation to a Jules session.
"""

import json
import re
from typing import Any, cast

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
            provider=ai_provider or "ollama", model=ai_model or "qwen3:1.7b", **(ai_config or {})
        )

    def run(self) -> dict[str, Any]:
        """Execute the Project Creator workflow."""
        self.log("Starting Project Creator workflow")

        try:
            idea_data = self.generate_project_idea()
            if not idea_data:
                return {"status": "failed", "reason": "could_not_generate_idea"}

            repo_name = idea_data.get("repository_name")
            project_idea = idea_data.get("idea_description")
            tech_stack = idea_data.get("tech_stack", "")

            if not repo_name or not project_idea:
                return {"status": "failed", "reason": "invalid_idea_format"}

            repo_name = re.sub(r"[^a-z0-9-]", "-", repo_name.lower())
            repo_name = re.sub(r"-+", "-", repo_name).strip("-")
            full_repo_name = f"{self.target_owner}/{repo_name}"

            self._notify_idea(repo_name, project_idea, tech_stack)

            instructions = self.load_jules_instructions(
                variables={
                    "repository_name": full_repo_name,
                    "project_idea": project_idea,
                    "tech_stack": tech_stack,
                }
            )

            repo = self._create_github_repo(repo_name, project_idea)
            if not repo:
                return {"status": "failed", "reason": "repo_creation_failed"}

            self.allowlist.add_repository(full_repo_name)
            session = self.create_jules_session(
                repository=full_repo_name,
                instructions=instructions,
                title=f"Initial implementation for {repo_name}",
                base_branch=getattr(repo, "default_branch", None),
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

        except Exception:
            self.log("Project Creator failed", "ERROR")
            self._notify_failed()
            return {"status": "failed"}

    def _notify_idea(self, repo_name: str, idea: str, tech_stack: str = "") -> None:
        if not self.telegram:
            return
        esc = self.telegram.escape_html
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
        try:
            self.telegram.send_message("\n".join(lines), parse_mode="HTML")
        except Exception:
            self.log("Failed to send idea notification", "WARNING")

    def _notify_created(
        self,
        full_repo_name: str,
        idea: str,
        task_url: str | None = None,
        repo_url: str | None = None,
    ) -> None:
        if not self.telegram:
            return
        esc = self.telegram.escape_html
        gh_url = repo_url or f"https://github.com/{full_repo_name}"
        text = (
            f"✅ <b>PROJETO CRIADO COM SUCESSO</b>\n"
            f"──────────────────────\n"
            f"📦 <b>Repositório:</b> <code>{esc(full_repo_name)}</code>\n"
            f"📝 <b>Ideia:</b> <i>{esc(idea[:250])}</i>\n"
            f"──────────────────────\n"
            f'🐙 <a href="{gh_url}">Ver no GitHub</a>'
        )
        buttons = [{"text": "🐙 GitHub", "url": gh_url}]
        if task_url:
            buttons.append({"text": "⚙️ Ver task opencode", "url": task_url})
        reply_markup = {"inline_keyboard": [buttons]}
        try:
            self.telegram.send_message(text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            self.log("Failed to send created notification", "WARNING")

    def _notify_failed(self) -> None:
        if not self.telegram:
            return
        text = (
            "❌ <b>PROJECT CREATOR — FALHA</b>\n"
            "──────────────────────\n"
            "Ocorreu um erro. Verifique os logs para detalhes."
        )
        try:
            self.telegram.send_message(text, parse_mode="HTML")
        except Exception:  # noqa: BLE001
            self.log("Failed to send failure notification", "WARNING")

    def _create_github_repo(self, repo_name: str, project_idea: str) -> Any | None:
        """Create a private GitHub repository for Vibe-Code implementation."""
        description = f"{project_idea[:250]} {_AUTONOMOUS_NOTICE}"[:350]
        user = cast(Any, self.github_client.g.get_user())
        if user.login.strip().lower() != self.target_owner.strip().lower():
            self.log(
                f"Refusing to create repository for authenticated owner {user.login}; "
                f"expected {self.target_owner}",
                "ERROR",
            )
            return None
        try:
            repo = user.create_repo(
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

    def _fetch_existing_repos(self) -> list[str]:
        """Fetch names of the user's existing repositories for context."""
        try:
            repos = self.github_client.get_user_repos(sort="updated", direction="desc")
            return [r.name for r in list(repos)[:40]]
        except Exception as e:
            self.log(f"Could not fetch existing repos: {e}", "WARNING")
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
            '  "idea_description": "A detailed 2-3 sentence description: what it does, who uses it, and why it is useful or fun.",\n'
            '  "tech_stack": "e.g. Python + FastAPI, or Node.js + TypeScript, or Go CLI"\n'
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
