"""PR SLA Agent - alerts on stale pull requests."""
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self._check_pr_stale, issue, stale_threshold): issue.id for issue in issues}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        stale.append(result)
                except Exception as exc:
                    self.log(f"Failed to inspect PR SLA: {exc}", "WARNING")

        esc = self.telegram.escape_html
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "⏱️ <b>PR SLA AGENT</b>",
            f"📅 <code>{esc(now)}</code>",
            f"👤 <b>Owner:</b> <code>{esc(self.target_owner)}</code>",
            "──────────────────────",
            f"🕒 <b>PRs sem atualização (&gt;24h):</b> <code>{len(stale)}</code>",
        ]
        for item in stale[:20]:
            hours = item["hours_without_update"]
            urgency = "🔴" if int(hours) >= 72 else "🟡"
            lines.append(
                f'{urgency} <a href="{esc(item["url"])}">{esc(item["repo"])} #{item["number"]}</a>'
                f" — <b>{esc(hours)}h</b> — <i>{esc(item['title'])}</i>"
            )

        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
        return {"agent": "pr-sla", "owner": self.target_owner, "stale_pull_requests": stale, "count": len(stale)}

    def _check_pr_stale(self, issue: Any, stale_threshold: datetime) -> dict | None:
        """Check if a single PR is stale. Thread-safe."""
        pr = self.github_client.get_pr_from_issue(issue)
        last_update = pr.updated_at or pr.created_at
        if last_update < stale_threshold:
            return {
                "repo": pr.base.repo.full_name,
                "number": str(pr.number),
                "title": pr.title,
                "url": pr.html_url,
                "hours_without_update": str(int((datetime.now(UTC) - last_update).total_seconds() // 3600)),
            }
        return None
