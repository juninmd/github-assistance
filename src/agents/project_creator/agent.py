"""
Project Creator Agent - Responsible for brainstorming ideas, running opencode to develop
the implementation locally, then creating the GitHub repository with the finished code.
"""
import json
import os
import re
import subprocess
import tempfile
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
        self._ai_client = get_ai_client(provider=ai_provider or "ollama", model=ai_model or "qwen3:1.7b", **(ai_config or {}))

    def run(self) -> dict[str, Any]:
        """Execute the Project Creator workflow."""
        self.log("Starting Project Creator workflow")

        try:
            idea_data = self.generate_project_idea()
            if not idea_data:
                return {"status": "failed", "reason": "could_not_generate_idea"}

            repo_name = idea_data.get("repository_name")
            project_idea = idea_data.get("idea_description")

            if not repo_name or not project_idea:
                return {"status": "failed", "reason": "invalid_idea_format"}

            repo_name = re.sub(r'[^a-z0-9-]', '-', repo_name.lower())
            repo_name = re.sub(r'-+', '-', repo_name).strip('-')
            full_repo_name = f"{self.target_owner}/{repo_name}"

            self._notify_idea(repo_name, project_idea)

            instructions = self.load_jules_instructions(
                variables={
                    "repository_name": full_repo_name,
                    "project_idea": project_idea,
                }
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                success, committed, output = self._develop_with_opencode(tmpdir, instructions)
                if not success or not committed:
                    return {"status": "failed", "reason": "opencode_produced_no_code", "output": output}

                repo = self._create_github_repo(repo_name, project_idea)
                if not repo:
                    return {"status": "failed", "reason": "repo_creation_failed"}

                pushed = self._push_to_github(tmpdir, repo_name)
                if not pushed:
                    return {"status": "failed", "reason": "push_failed"}

            self.allowlist.add_repository(full_repo_name)
            self._notify_created(full_repo_name, project_idea)
            return {"status": "success", "repository": full_repo_name, "idea": project_idea}

        except Exception as e:
            self.log(f"Project Creator failed: {e}", "ERROR")
            self._notify_failed(str(e))
            return {"status": "failed", "error": str(e)}

    def _notify_idea(self, repo_name: str, idea: str) -> None:
        if not self.telegram:
            return
        esc = self.telegram.escape_html
        lines = [
            "💡 <b>NOVA IDEIA DE PROJETO</b>",
            "──────────────────────",
            f"📦 <b>Repositório:</b> <code>{esc(repo_name)}</code>",
            "📝 <b>Descrição:</b>",
            f"<i>{esc(idea)}</i>",
            "──────────────────────",
            "⚙️ Desenvolvendo com opencode…",
        ]
        try:
            self.telegram.send_message("\n".join(lines), parse_mode="HTML")
        except Exception as exc:
            self.log(f"Failed to send idea notification: {exc}", "WARNING")

    def _notify_created(self, full_repo_name: str, idea: str) -> None:
        if not self.telegram:
            return
        esc = self.telegram.escape_html
        url = f"https://github.com/{full_repo_name}"
        text = (
            f"✅ <b>REPOSITÓRIO CRIADO</b>\n"
            f"──────────────────────\n"
            f"📦 <b>Repositório:</b> <code>{esc(full_repo_name)}</code>\n"
            f"📝 <b>Ideia:</b> <i>{esc(idea[:200])}</i>\n"
            f"──────────────────────\n"
            f"🔗 <a href=\"{url}\">Abrir no GitHub</a>"
        )
        reply_markup = {"inline_keyboard": [[{"text": "🔗 Ver repositório", "url": url}]]}
        try:
            self.telegram.send_message(text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as exc:
            self.log(f"Failed to send created notification: {exc}", "WARNING")

    def _notify_failed(self, error: str) -> None:
        if not self.telegram:
            return
        text = (
            f"❌ <b>PROJECT CREATOR — FALHA</b>\n"
            f"──────────────────────\n"
            f"<pre>{self.telegram.escape_html(error[:300])}</pre>"
        )
        try:
            self.telegram.send_message(text, parse_mode="HTML")
        except Exception as exc:
            self.log(f"Failed to send failure notification: {exc}", "WARNING")

    def _develop_with_opencode(self, tmpdir: str, instructions: str) -> tuple[bool, bool, str]:
        """Initialize a local git repo, run opencode to implement the project, commit changes."""
        model = self._get_random_free_opencode_model()
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-assistance@github.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "github-assistance"], cwd=tmpdir, capture_output=True)

        # Warm up opencode (first run does DB migration and exits)
        self.log("Warming up opencode (first-run DB migration)...")
        subprocess.run(
            ["opencode", "run", "--model", model, "ping"],
            capture_output=True, text=True, timeout=120, cwd=tmpdir,
        )

        self.log("Running opencode to develop project...")
        run_result = subprocess.run(
            ["opencode", "run", "--model", model, instructions],
            capture_output=True, text=True, timeout=600, cwd=tmpdir,
        )
        if run_result.returncode != 0:
            self.log(f"opencode failed (rc={run_result.returncode}): {run_result.stderr}", "WARNING")
            return False, False, run_result.stderr[:500]

        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        commit_result = subprocess.run(
            ["git", "commit", "-m", "feat: initial project implementation via opencode\n\nAutonomously created by the github-assistance AI agent."],
            cwd=tmpdir, capture_output=True, text=True,
        )
        if "nothing to commit" in commit_result.stdout + commit_result.stderr:
            self.log("opencode made no file changes.")
            return True, False, run_result.stdout[:500]

        return True, True, run_result.stdout[:500]

    def _create_github_repo(self, repo_name: str, project_idea: str) -> Any | None:
        """Create a private GitHub repository without auto-init (code will be pushed from local)."""
        description = f"{project_idea[:250]} {_AUTONOMOUS_NOTICE}"[:350]
        user = self.github_client.g.get_user()
        try:
            repo = user.create_repo(
                name=repo_name,
                description=description,
                private=True,
                auto_init=False,
            )
            self.log(f"Created repository: {self.target_owner}/{repo_name}")
            return repo
        except GithubException as e:
            self.log(f"Failed to create repository: {e.status} {e.data}", "ERROR")
            return None
        except Exception as e:
            self.log(f"Unexpected error creating repository: {e}", "ERROR")
            return None

    def _push_to_github(self, tmpdir: str, repo_name: str) -> bool:
        """Add GitHub remote and push the local commits."""
        github_token = os.getenv("GITHUB_TOKEN", "")
        remote_url = f"https://{github_token}@github.com/{self.target_owner}/{repo_name}.git"

        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=tmpdir, capture_output=True)

        push_result = subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=tmpdir, capture_output=True, text=True, timeout=60,
        )
        if push_result.returncode != 0:
            self.log(f"Git push failed: {push_result.stderr}", "ERROR")
            return False

        self.log(f"Pushed code to {self.target_owner}/{repo_name}")
        return True

    def generate_project_idea(self) -> dict[str, Any] | None:
        """Use AI to brainstorm a new project idea."""
        if not self._ai_client:
            self.log("AI client is not configured.", "ERROR")
            return None

        prompt = (
            "You are a visionary software engineer looking to build a new fun, exciting, and highly profitable "
            "project using Artificial Intelligence.\n"
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
