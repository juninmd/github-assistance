"""Issue Escalation Agent - escalates stale critical issues to Telegram."""
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent


class IssueEscalationAgent(BaseAgent):
    def __init__(self, *args, target_owner: str = "juninmd", **kwargs):
        super().__init__(*args, name="issue_escalation", **kwargs)
        self.target_owner = target_owner

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def _escape(self, text: str) -> str:
        if not text:
            return ""
        for char in ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            text = text.replace(char, f"\\{char}")
        return text

    def run(self) -> dict[str, Any]:
        stale_threshold = datetime.now(UTC) - timedelta(days=7)
        query = f"is:issue is:open archived:false user:{self.target_owner} label:bug"
        issues = self.github_client.g.search_issues(query)

        escalations: list[dict[str, str]] = []
        for issue in issues:
            try:
                assignee = issue.assignee.login if issue.assignee else "unassigned"
                if issue.updated_at < stale_threshold or assignee == "unassigned":
                    escalations.append(
                        {
                            "repo": issue.repository.full_name,
                            "number": str(issue.number),
                            "title": issue.title,
                            "url": issue.html_url,
                            "assignee": assignee,
                        }
                    )
            except Exception as exc:
                self.log(f"Failed to inspect issue escalation: {exc}", "WARNING")

        lines = [
            "🚨 *Issue Escalation Agent*",
            f"👤 Owner: `{self._escape(self.target_owner)}`",
            f"📌 Issues para escalonamento: *{len(escalations)}*",
        ]
        for item in escalations[:20]:
            lines.append(
                f"• [{self._escape(item['repo'])}\\#{item['number']}]({item['url']}) - {self._escape(item['assignee'])}: {self._escape(item['title'])}"
            )

        self.github_client.send_telegram_msg("\n".join(lines), parse_mode="MarkdownV2")
        return {"agent": "issue-escalation", "owner": self.target_owner, "issues": escalations, "count": len(escalations)}
