"""
Jules Tracker Agent - Monitors active Jules sessions and answers questions.
"""

from typing import Any

from src.agents import utils as agent_utils
from src.agents.base_agent import BaseAgent
from src.agents.jules_tracker import utils
from src.ai import get_ai_client


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
        ai_enabled: bool = True,
        target_owner: str = "juninmd",
        **kwargs,
    ):
        super().__init__(*args, name="jules_tracker", enforce_repository_allowlist=False, **kwargs)
        self.target_owner = target_owner
        self.ai_client = None
        if ai_enabled:
            self.ai_client = get_ai_client(
                provider=ai_provider or "litellm", model=ai_model or "cloud/llama-70b", **(ai_config or {})
            )

    def run(self) -> dict[str, Any]:
        """
        Execute the Jules Tracker workflow:
        1. Fetch active sessions.
        2. Check their activities for pending questions from Jules.
        3. Answer them using the AI client.
        """
        self.log("Starting Jules Tracker workflow")

        # Do not call GitHub here: Jules tracking must keep clearing sessions
        # even when GH_PAT is expired or repository metadata is unavailable.
        repositories = self.allowlist.list_repositories()

        results: dict[str, Any] = {"answered_questions": [], "reviewed_plans": [], "failed": []}

        # 1. Fetch active sessions (limit to 1 page for speed — full pagination is too slow)
        try:
            sessions = self.jules_client.list_sessions(page_size=50, max_pages=1)
        except Exception:
            self.log("Failed to list sessions", "ERROR")
            results["failed"].append({"error": "Failed to list sessions"})
            self.telegram.send_message(
                "❌ <b>JULES TRACKER — ERRO AO LISTAR SESSÕES</b>\n"
                "<pre>Verifique os logs para detalhes.</pre>",
                parse_mode="HTML",
            )
            return results

        known_states = {"IN_PROGRESS", "AWAITING_USER_FEEDBACK"}

        def _is_active(session: dict[str, Any]) -> bool:
            state = session.get("state", session.get("status"))
            return state in known_states

        active_sessions = [s for s in sessions if _is_active(s)]

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
                if utils.is_plan_pending(activities):
                    self._handle_plan_approval(session_id, repo_match, session, activities, results)
                    continue

                question_text = utils.get_pending_question(session, activities)
                if not question_text:
                    if session.get("state", session.get("status")) != "AWAITING_USER_FEEDBACK":
                        continue
                    if utils.latest_activity_is_user_reply(activities):
                        continue
                    # Jules is blocked but didn't surface a clear question — unblock it.
                    question_text = "Jules is awaiting user feedback but no specific question was detected."
                session_url = session.get("url") or ""

                question_description = utils.format_question_description(
                    repo_match, session_id, question_text
                )

                self.log(
                    utils.format_question_log(
                        repo_match,
                        session_id,
                        session_url,
                        question_text,
                        self.QUESTION_COLOR,
                        self.RESET_COLOR,
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

                if self.ai_client is None:
                    answer = utils.DEFAULT_UNBLOCKING_ANSWER
                else:
                    try:
                        answer = self.ai_client.generate(prompt)
                    except Exception as e:
                        self.log(
                            f"AI answer failed for session {session_id}; using default unblock answer: {e}",
                            "WARNING",
                        )
                        answer = utils.DEFAULT_UNBLOCKING_ANSWER
                answer = utils.ensure_open_pr_request(answer)
                self.log(utils.format_answer_log(answer, self.ANSWER_COLOR, self.RESET_COLOR))

                self.jules_client.send_message(session_id, answer)
                utils.send_telegram_update(
                    self.telegram, repo_match, session_id, session_url, question_text, answer
                )

                results["answered_questions"].append(
                    {
                        "session_id": session_id,
                        "session_url": session_url,
                        "repository": repo_match,
                        "question_description": question_description,
                        "question": question_text,
                        "answer": answer,
                    }
                )
            except Exception as e:
                self.log(f"Failed to process session {session_id}: {e}", "ERROR")
                results["failed"].append({"session_id": session_id, "error": str(e)})
                self.telegram.send_message(
                    f"❌ <b>JULES TRACKER — ERRO SESSÃO</b>\n"
                    f"🆔 <code>{self.telegram.escape_html(str(session_id))}</code>\n"
                    "<pre>Verifique os logs para detalhes.</pre>",
                    parse_mode="HTML",
                )

        self.log(f"Completed: answered {len(results['answered_questions'])} questions")

        # Isolated on purpose: the loop above must keep unblocking Jules sessions
        # even when GH_PAT is missing/expired, since it only needs JULES_API_KEY.
        # This step is the first GitHub call in this agent, so a failure here
        # (e.g. bad token) must never affect the result/status of the work above.
        results["roadmap_started"] = []
        try:
            self._advance_roadmap_issues(results)
        except Exception as e:
            self.log(f"Roadmap advancement skipped: {e}", "WARNING")

        self._send_summary(results)
        if results["failed"]:
            results["status"] = "failed"
        return results

    def _advance_roadmap_issues(self, results: dict[str, Any]) -> None:
        """Start the next roadmap item (label 'jules') for repos with none in flight.

        One issue at a time per repository: if any open issue already carries the
        'jules' label, a session is presumably still working on it, so we skip.
        Labeling an issue 'jules' natively triggers a Jules session (validated via
        the Jules API — see project_creator/agent.py:_create_roadmap_backlog).
        """
        for repository in self.allowlist.list_repositories():
            try:
                repo_info = self.get_repository_info(repository)
                if not repo_info:
                    continue
                open_issues = list(repo_info.get_issues(state="open"))
                if any(
                    agent_utils.issue_has_label(i, agent_utils.ROADMAP_ACTIVE_LABEL)
                    for i in open_issues
                ):
                    continue
                roadmap_issues = [
                    i for i in open_issues if agent_utils.issue_has_label(i, agent_utils.ROADMAP_LABEL)
                ]
                if not roadmap_issues:
                    continue
                next_issue = min(roadmap_issues, key=lambda i: i.number)
                next_issue.add_to_labels(agent_utils.ROADMAP_ACTIVE_LABEL)
                self.log(f"Started roadmap item #{next_issue.number} for {repository}")
                results["roadmap_started"].append(
                    {"repository": repository, "issue": next_issue.number, "url": next_issue.html_url}
                )
            except Exception as e:
                self.log(f"Failed to advance roadmap for {repository}: {e}", "WARNING")

    def _handle_plan_approval(
        self,
        session_id: str,
        repository: str,
        session: dict[str, Any],
        activities: list[dict[str, Any]],
        results: dict[str, Any],
    ) -> None:
        """Review a plan awaiting approval: approve it or request changes via text."""
        session_url = session.get("url") or ""
        plan_text = utils.get_pending_plan(activities) or (session.get("statusMessage") or "").strip()
        if not plan_text:
            return

        prompt = f"""You are the user reviewing an implementation plan proposed by an AI developer agent (Jules).
Repository: {repository}
Session: {session_id}

Jules proposed the following plan and is waiting for approval before starting work:
\"\"\"{plan_text}\"\"\"

If the plan looks safe and reasonable, respond with EXACTLY: APPROVE
Otherwise, respond with the concise feedback/changes Jules should apply before proceeding (do not include the word APPROVE)."""

        if self.ai_client is None:
            decision = "APPROVE"
        else:
            try:
                decision = self.ai_client.generate(prompt).strip()
            except Exception as e:
                self.log(
                    f"AI plan review failed for session {session_id}; approving by default: {e}",
                    "WARNING",
                )
                decision = "APPROVE"

        if decision.upper().startswith("APPROVE"):
            self.jules_client.approve_plan(session_id)
            self.jules_client.send_message(session_id, utils.OPEN_PR_INSTRUCTION)
            action = "approved"
        else:
            decision = utils.ensure_open_pr_request(decision)
            self.jules_client.send_message(session_id, decision)
            action = "changes_requested"

        utils.send_plan_telegram_update(self.telegram, repository, session_id, session_url, plan_text, decision)
        results["reviewed_plans"].append(
            {
                "session_id": session_id,
                "session_url": session_url,
                "repository": repository,
                "action": action,
            }
        )

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        answered = results.get("answered_questions", [])
        reviewed_plans = results.get("reviewed_plans", [])
        roadmap_started = results.get("roadmap_started", [])
        failed = results.get("failed", [])
        lines = [
            "🤖 <b>JULES TRACKER</b>",
            "──────────────────────",
            f"💬 <b>Perguntas respondidas:</b> <code>{len(answered)}</code>",
            f"📋 <b>Planos revisados:</b> <code>{len(reviewed_plans)}</code>",
            f"🗺️ <b>Itens de roadmap iniciados:</b> <code>{len(roadmap_started)}</code>",
            f"❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for item in answered[:5]:
            url = item.get("session_url", "")
            repo = item.get("repository", "")
            lines.append(f'  └ <a href="{esc(url)}">{esc(repo)}</a>')
        for item in roadmap_started[:5]:
            url = item.get("url", "")
            repo = item.get("repository", "")
            lines.append(f'  └ 🗺️ <a href="{esc(url)}">{esc(repo)} #{item.get("issue")}</a>')
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
