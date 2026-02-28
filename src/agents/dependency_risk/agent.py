"""Dependency Risk Agent - classifies dependency PR risk and notifies Telegram."""
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent


class DependencyRiskAgent(BaseAgent):
    def __init__(self, *args, target_owner: str = "juninmd", **kwargs):
        super().__init__(*args, name="dependency_risk", **kwargs)
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

    def _risk_level(self, title: str, body: str) -> str:
        content = f"{title} {body}".lower()
        if "security" in content or "cve" in content:
            return "alto"
        if "major" in content or "breaking" in content:
            return "alto"
        if "minor" in content:
            return "medio"
        return "baixo"

    def run(self) -> dict[str, Any]:
        cutoff = datetime.now(UTC) - timedelta(days=14)
        query = (
            f"is:pr is:open archived:false user:{self.target_owner} "
            f"(author:dependabot[bot] OR author:renovate[bot])"
        )
        issues = self.github_client.search_prs(query)

        findings: list[dict[str, str]] = []
        for issue in issues:
            try:
                pr = self.github_client.get_pr_from_issue(issue)
                if pr.created_at < cutoff:
                    continue
                risk = self._risk_level(pr.title or "", pr.body or "")
                findings.append(
                    {
                        "repo": pr.base.repo.full_name,
                        "number": str(pr.number),
                        "title": pr.title,
                        "url": pr.html_url,
                        "risk": risk,
                    }
                )
            except Exception as exc:
                self.log(f"Failed to inspect dependency PR: {exc}", "WARNING")

        risk_order = {"alto": 0, "medio": 1, "baixo": 2}
        findings.sort(key=lambda item: risk_order.get(item["risk"], 9))

        lines = [
            "📦 *Dependency Risk Agent*",
            f"👤 Owner: `{self._escape(self.target_owner)}`",
            f"🔎 PRs analisados \\(14 dias\\): *{len(findings)}*",
        ]
        for item in findings[:20]:
            lines.append(
                f"• [{self._escape(item['repo'])}\\#{item['number']}]({item['url']}) - {self._escape(item['risk'])}: {self._escape(item['title'])}"
            )

        self.github_client.send_telegram_msg("\n".join(lines), parse_mode="MarkdownV2")
        return {"agent": "dependency-risk", "owner": self.target_owner, "pull_requests": findings, "count": len(findings)}
