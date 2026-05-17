"""PR SLA Agent - alerts on stale pull requests and auto-nudges reviewers."""
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent

_NUDGE_LABEL = "sla-breach"
_NUDGE_COMMENT = (
    "⏱️ **SLA Alert — revisão pendente**\n\n"
    "Este pull request está sem atualização há **{hours}h** e ultrapassou o SLA de 24h.\n\n"
    "Por favor, um dos revisores avalie ou deixe um comentário com o status.\n\n"
    "---\n"
    "🤖 **Origem Automatizada**\n"
    "- **Agente:** `pr_sla`\n"
    "- **Modelo:** N/A (regra determinística)\n"
    "- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)"
)


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
        nudged: list[str] = []

        for issue in issues:
            try:
                pr = self.github_client.get_pr_from_issue(issue)
                last_update = pr.updated_at or pr.created_at
                if last_update < stale_threshold:
                    hours = int((datetime.now(UTC) - last_update).total_seconds() // 3600)
                    entry = {
                        "repo": pr.base.repo.full_name,
                        "number": str(pr.number),
                        "title": pr.title,
                        "url": pr.html_url,
                        "hours_without_update": str(hours),
                    }
                    stale.append(entry)
                    nudged_url = self._nudge_pr(pr, hours)
                    if nudged_url:
                        nudged.append(nudged_url)
            except Exception as exc:
                self.log(f"Failed to inspect PR SLA: {exc}", "WARNING")

        self._send_summary(stale, nudged)
        return {"agent": "pr-sla", "owner": self.target_owner, "stale_pull_requests": stale, "count": len(stale), "nudged": nudged}

    def _nudge_pr(self, pr: Any, hours: int) -> str | None:
        """Post a SLA-breach comment on the PR if not already nudged recently."""
        try:
            comments = list(pr.get_issue_comments())
            already_nudged = any(
                "SLA Alert" in (c.body or "") and "github-assistance" in (c.body or "")
                for c in comments[-5:]
            )
            if already_nudged:
                return None
            comment = pr.create_issue_comment(_NUDGE_COMMENT.format(hours=hours))
            self.log(f"Nudged PR #{pr.number} in {pr.base.repo.full_name} ({hours}h stale)")
            return comment.html_url
        except Exception as exc:
            self.log(f"Failed to nudge PR #{pr.number}: {exc}", "WARNING")
            return None

    def _send_summary(self, stale: list, nudged: list) -> None:
        esc = self.telegram.escape_html
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "⏱️ <b>PR SLA AGENT</b>",
            f"📅 <code>{esc(now)}</code>",
            f"👤 <b>Owner:</b> <code>{esc(self.target_owner)}</code>",
            "──────────────────────",
            f"🕒 <b>PRs sem atualização (&gt;24h):</b> <code>{len(stale)}</code>",
            f"💬 <b>Nudges enviados:</b> <code>{len(nudged)}</code>",
        ]
        for item in stale[:20]:
            hours = item["hours_without_update"]
            urgency = "🔴" if int(hours) >= 72 else "🟡"
            lines.append(
                f'{urgency} <a href="{esc(item["url"])}">{esc(item["repo"])} #{item["number"]}</a>'
                f" — <b>{esc(hours)}h</b> — <i>{esc(item['title'])}</i>"
            )

        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
