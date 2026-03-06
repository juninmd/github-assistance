"""Dependency Risk Agent - classifies dependency PR risk and notifies Telegram."""
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent

CVSS_PATTERN = re.compile(r"cvss[:\s]*(\d+\.?\d*)", re.IGNORECASE)
SEVERITY_PATTERN = re.compile(r"severity[:\s]*(critical|high|moderate|medium|low)", re.IGNORECASE)
SEMVER_MAJOR_PATTERN = re.compile(r"(\d+)\.\d+\.\d+\s*→\s*(\d+)\.\d+\.\d+")

HIGH_RISK_KEYWORDS = {"vulnerability", "exploit", "remote code execution", "rce", "cve", "security"}
MEDIUM_RISK_KEYWORDS = {"breaking", "deprecated", "major"}


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

    def _risk_level(self, title: str, body: str) -> str:
        content = f"{title} {body}".lower()

        # Check CVSS score first (most reliable signal)
        cvss_match = CVSS_PATTERN.search(content)
        if cvss_match:
            score = float(cvss_match.group(1))
            if score >= 7.0:
                return "alto"
            if score >= 4.0:
                return "medio"
            return "baixo"

        # Check explicit severity labels
        severity_match = SEVERITY_PATTERN.search(content)
        if severity_match:
            level = severity_match.group(1).lower()
            if level in {"critical", "high"}:
                return "alto"
            if level in {"moderate", "medium"}:
                return "medio"
            return "baixo"

        # Check for major version bumps (e.g., 2.x.x → 3.x.x)
        semver_match = SEMVER_MAJOR_PATTERN.search(content)
        if semver_match and semver_match.group(1) != semver_match.group(2):
            return "alto"

        # Keyword-based fallback
        if any(kw in content for kw in HIGH_RISK_KEYWORDS):
            return "alto"
        if any(kw in content for kw in MEDIUM_RISK_KEYWORDS):
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

        esc = self.telegram.escape
        lines = [
            "📦 *Dependency Risk Agent*",
            f"👤 Owner: `{esc(self.target_owner)}`",
            f"🔎 PRs analisados \\(14 dias\\): *{len(findings)}*",
        ]
        for item in findings[:20]:
            lines.append(
                f"• [{esc(item['repo'])}\\#{item['number']}]({item['url']}) - {esc(item['risk'])}: {esc(item['title'])}"
            )

        self.telegram.send_message("\n".join(lines), parse_mode="MarkdownV2")
        return {"agent": "dependency-risk", "owner": self.target_owner, "pull_requests": findings, "count": len(findings)}
