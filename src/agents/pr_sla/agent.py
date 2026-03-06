"""PR SLA Agent - alerts on stale pull requests."""
from datetime import UTC, datetime, timedelta
from typing import Any

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

    def run(self) -> dict[str, Any]:
        stale_threshold = datetime.now(UTC) - timedelta(hours=24)
        query = f"is:pr is:open archived:false user:{self.target_owner}"
        issues = self.github_client.search_prs(query)

        stale: list[dict[str, str]] = []
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
                            "hours_without_update": str(int((datetime.now(UTC) - last_update).total_seconds() // 3600)),
                        }
                    )
            except Exception as exc:
                self.log(f"Failed to inspect PR SLA: {exc}", "WARNING")

        esc = self.telegram.escape
        lines = [
            "⏱️ *PR SLA Agent*",
            f"👤 Owner: `{esc(self.target_owner)}`",
            f"🕒 PRs sem atualização \\(\\>24h\\): *{len(stale)}*",
        ]
        for item in stale[:20]:
            lines.append(
                f"• [{esc(item['repo'])}\\#{item['number']}]({item['url']}) - {item['hours_without_update']}h: {esc(item['title'])}"
            )

        self.telegram.send_message("\n".join(lines), parse_mode="MarkdownV2")
        return {"agent": "pr-sla", "owner": self.target_owner, "stale_pull_requests": stale, "count": len(stale)}
