"""
Jules Tracker Agent - Monitors active Jules sessions and answers questions.
"""
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client


class JulesTrackerAgent(BaseAgent):
    """
    Jules Tracker Agent
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
            session_id = session.get("name") or session.get("id")
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
                if not activities:
                    continue

                # Check the most recent activity
                latest_activity = activities[0]
                # Look for a question waiting for user input
                if session.get("state", session.get("status")) == "AWAITING_USER_FEEDBACK" or "agentMessaged" in latest_activity:
                    question_text = latest_activity.get("agentMessaged", {}).get("agentMessage", "") or session.get("statusMessage", "Awaiting input")

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked a question or is waiting for input.

Below is the question from Jules, delimited by <question> and </question> tags. Please provide a helpful, concise, and direct answer so Jules can continue its work. If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default.

<question>
{question_text}
</question>"""

                    self.log(f"Found pending question in session {session_id} for repo {repo_match}: {question_text}")

                    prompt = f"""You are the user interacting with an AI developer agent (Jules).
Jules is working on the repository {repo_match} and has asked the following question or is waiting for input:
"{question_text}"

Please provide a helpful, concise, and direct answer so Jules can continue its work.
If you don't know the exact answer, instruct Jules to proceed with its best judgement or provide a safe default."""

                    answer = self.ai_client.generate(prompt)
                    self.log(f"Generated answer: {answer}")

                    self.jules_client.send_message(session_id, answer)

                    results["answered_questions"].append({
                        "session_id": session_id,
                        "repository": repo_match,
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
