"""PR SLA Agent - alerts on stale pull requests."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from src.agents.base_agent import BaseAgent


class PRSLAAgent(BaseAgent):
    def __init__(self, *args, target_owner: str = "juninmd", **kwargs):
        super().__init__(*args, name="pr_sla", **kwargs)
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

    def run(self) -> Dict[str, Any]:
        stale_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
        query = f"is:pr is:open archived:false user:{self.target_owner}"
        issues = self.github_client.search_prs(query)

        stale: List[Dict[str, str]] = []
        for issue in issues:
            try:
                pr = self.github_client.get_pr_from_issue(issue)
                last_update = pr.updated_at or pr.created_at
                if last_update < stale_threshold:
                    stale.append(
                        {
                            "repo": pr.base.repo.full_name,
                            "number": str(pr.number),
                            "title": pr.title,
                            "url": pr.html_url,
                            "hours_without_update": str(int((datetime.now(timezone.utc) - last_update).total_seconds() // 3600)),
                        }
                    )
            except Exception as exc:
                self.log(f"Failed to inspect PR SLA: {exc}", "WARNING")

        lines = [
            "⏱️ *PR SLA Agent*",
            f"👤 Owner: `{self._escape(self.target_owner)}`",
            f"🕒 PRs sem atualização \\(\\>24h\\): *{len(stale)}*",
        ]
        for item in stale[:20]:
            lines.append(
                f"• [{self._escape(item['repo'])}\\#{item['number']}]({item['url']}) - {item['hours_without_update']}h: {self._escape(item['title'])}"
            )

        self.github_client.send_telegram_msg("\n".join(lines), parse_mode="MarkdownV2")
        return {"agent": "pr-sla", "owner": self.target_owner, "stale_pull_requests": stale, "count": len(stale)}
