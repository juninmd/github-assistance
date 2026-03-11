"""
Jules Tracker Agent - Monitors active Jules sessions and answers questions.
"""
import os
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client


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
        super().__init__(*args, name="jules_tracker", **kwargs)
        self.target_owner = target_owner
        self.ai_client = get_ai_client(
            provider=ai_provider or "gemini",
            model=ai_model or "gemini-2.5-flash",
            **(ai_config or {})
        )

    def _get_pending_question(
        self,
        session: dict[str, Any],
        activities: list[dict[str, Any]],
    ) -> str | None:
        """Return the latest unanswered Jules message for the session."""
        ordered_activities = sorted(activities, key=lambda activity: activity.get("createTime", ""))
        last_user_reply_index = -1
        pending_question: str | None = None

        for index, activity in enumerate(ordered_activities):
            if "userMessaged" in activity:
                last_user_reply_index = index
                pending_question = None
                continue

            message = activity.get("agentMessaged", {}).get("agentMessage", "").strip()
            if message and index > last_user_reply_index:
                pending_question = message

        if pending_question:
            return pending_question

        status_message = (session.get("statusMessage") or "").strip()
        if session.get("state", session.get("status")) == "AWAITING_USER_FEEDBACK" and status_message:
            return status_message

        return None

    def _format_question_description(
        self,
        repository: str,
        session_id: str,
        question_text: str,
    ) -> str:
        """Build a readable label that makes the repository obvious in logs/results."""
        return f"[{repository}] session {session_id}: {question_text}"

    def _colorize(self, text: str, color: str) -> str:
        """Colorize terminal output unless explicitly disabled."""
        if os.getenv("NO_COLOR"):
            return text
        return f"{color}{text}{self.RESET_COLOR}"

    def _format_question_log(
        self,
        repository: str,
        session_id: str,
        session_url: str,
        question_text: str,
    ) -> str:
        """Build a multi-line log entry with the key session details."""
        return (
            "Found pending question\n"
            f"  Repository: {repository}\n"
            f"  Session: {session_id}\n"
            f"  URL: {session_url}\n"
            f"  Question: {self._colorize(question_text, self.QUESTION_COLOR)}"
        )

    def _format_answer_log(self, answer: str) -> str:
        """Build a colored answer log block."""
        return f"Generated answer\n  LLM: {self._colorize(answer, self.ANSWER_COLOR)}"

    def _send_telegram_update(
        self,
        repository: str,
        session_id: str,
        session_url: str,
        question_text: str,
        answer: str,
    ) -> None:
        """Forward the Jules question and LLM answer to Telegram."""
        esc = self.telegram.escape
        lines = [
            "🤖 *Jules Tracker*",
            f"📦 *Repositorio:* `{esc(repository)}`",
            f"🧵 *Sessao:* `{esc(session_id)}`",
            f"❓ *Pergunta do Jules:*\n{esc(question_text)}",
            f"🧠 *Resposta do LLM:*\n{esc(answer)}",
            f"🔗 *Sessao Jules:* {esc(session_url)}",
        ]
        self.telegram.send_message("\n\n".join(lines), parse_mode="MarkdownV2")

    def run(self) -> dict[str, Any]:
        """
        Execute the Jules Tracker workflow:
        1. Fetch active sessions.
        2. Check their activities for pending questions from Jules.
        3. Answer them using the AI client.
        """
        self.log("Starting Jules Tracker workflow")

        repositories = self.get_allowed_repositories()
        if not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results: dict[str, Any] = {
            "answered_questions": [],
            "failed": []
        }

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

            # Ensure session is related to an allowed repository
            source_context = session.get("sourceContext", {})
            source = source_context.get("source", "")

            repo_match = None
            for repo in repositories:
                if repo in source:
                    repo_match = repo
                    break

            if not repo_match:
                continue

            try:
                activities = self.jules_client.list_activities(session_id)
                question_text = self._get_pending_question(session, activities)
                if not question_text:
                    continue
                session_url = session.get("url") or "URL not provided by Jules API"

                question_description = self._format_question_description(
                    repo_match,
                    session_id,
                    question_text,
                )

                self.log(
                    self._format_question_log(
                        repo_match,
                        session_id,
                        session_url,
                        question_text,
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
                self.log(self._format_answer_log(answer))

                self.jules_client.send_message(session_id, answer)
                self._send_telegram_update(
                    repo_match,
                    session_id,
                    session_url,
                    question_text,
                    answer,
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
                results["failed"].append({
                    "session_id": session_id,
                    "error": str(e)
                })

        self.log(f"Completed: answered {len(results['answered_questions'])} questions")
        return results
