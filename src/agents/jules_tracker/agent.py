"""
Jules Tracker Agent - Monitors active Jules sessions and answers questions.
"""
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client
from src.agents.jules_tracker import utils


class JulesTrackerAgent(BaseAgent):
    """
    Jules Tracker Agent
    """

    QUESTION_COLOR = "\033[96m"
    ANSWER_COLOR = "\033[92m"
    RESET_COLOR = "\033[0m"

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
        target_owner: str = "juninmd",
        **kwargs,
    ):
        super().__init__(*args, name="jules_tracker", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = target_owner
        self.ai_client = get_ai_client(
            provider=ai_provider or "ollama",
            model=ai_model or "qwen3:1.7b",
            **(ai_config or {})
        )

    def run(self) -> dict[str, Any]:
        """
        Execute the Jules Tracker workflow:
        1. Fetch active sessions.
        2. Check their activities for pending questions from Jules.
        3. Answer them using the AI client.
        """
        self.log("Starting Jules Tracker workflow")

        repositories = self.get_allowed_repositories()
        if self.uses_repository_allowlist() and not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results: dict[str, Any] = {"answered_questions": [], "failed": []}

        # 1. Fetch active sessions (we list all and filter)
        try:
            sessions = self.jules_client.list_sessions(page_size=100)
        except Exception as e:
            self.log(f"Failed to list sessions: {e}", "ERROR")
            results["failed"].append({"error": f"Failed to list sessions: {e}"})
            return results

        active_states = ["IN_PROGRESS", "AWAITING_USER_FEEDBACK"]
        active_sessions = [s for s in sessions if s.get("state", s.get("status")) in active_states]

        for session in active_sessions:
            session_id = session.get("id") or session.get("name")
            if not session_id:
                continue

            repo_name = utils.extract_repository_name(session)
            repo_match = repo_name

            if self.uses_repository_allowlist():
                repo_match = next((repo for repo in repositories if repo == repo_name), None)

            if not repo_match:
                continue

            try:
                activities = self.jules_client.list_activities(session_id)
                question_text = utils.get_pending_question(session, activities)
                if not question_text:
                    continue
                session_url = session.get("url") or "URL not provided by Jules API"

                question_description = utils.format_question_description(
                    repo_match, session_id, question_text
                )

                self.log(
                    utils.format_question_log(
                        repo_match, session_id, session_url, question_text,
                        self.QUESTION_COLOR, self.RESET_COLOR
                    )
                )

                prompt = f"""You are the user interacting with an AI developer agent (Jules).
Repository: {repo_match}
Session: {session_id}
Session URL: {session_url}

Jules has asked the following question or is waiting for input:
"{question_text}"

Please provide a helpful, concise, and direct answer so Jules can continue its work.
If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default."""

                answer = self.ai_client.generate(prompt)
                self.log(utils.format_answer_log(answer, self.ANSWER_COLOR, self.RESET_COLOR))

                self.jules_client.send_message(session_id, answer)
                utils.send_telegram_update(
                    self.telegram, repo_match, session_id, session_url, question_text, answer
                )

                results["answered_questions"].append({
                    "session_id": session_id,
                    "session_url": session_url,
                    "repository": repo_match,
                    "question_description": question_description,
                    "question": question_text,
                    "answer": answer
                })
            except Exception as e:
                self.log(f"Failed to process session {session_id}: {e}", "ERROR")
                results["failed"].append({"session_id": session_id, "error": str(e)})

        self.log(f"Completed: answered {len(results['answered_questions'])} questions")
        return results
