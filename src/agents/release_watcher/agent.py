"""Release Watcher Agent - summarizes recent releases and alerts Telegram."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from src.agents.base_agent import BaseAgent


class ReleaseWatcherAgent(BaseAgent):
    def __init__(self, *args, target_owner: str = "juninmd", **kwargs):
        super().__init__(*args, name="release_watcher", **kwargs)
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
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        repos = self.get_allowed_repositories()
        if not repos:
            repos = [repo.full_name for repo in self.github_client.g.get_user(self.target_owner).get_repos()]

        releases: List[Dict[str, str]] = []
        for repo_name in repos:
            try:
                repo = self.github_client.get_repo(repo_name)
                for release in repo.get_releases()[:10]:
                    created_at = release.created_at or release.published_at
                    if created_at and created_at < cutoff:
                        break
                    releases.append(
                        {
                            "repo": repo.full_name,
                            "tag": release.tag_name or "sem-tag",
                            "name": release.title or release.tag_name or "release",
                            "url": release.html_url,
                            "draft": "sim" if release.draft else "não",
                            "prerelease": "sim" if release.prerelease else "não",
                        }
                    )
            except Exception as exc:
                self.log(f"Failed to inspect releases for {repo_name}: {exc}", "WARNING")

        lines = [
            "🚀 *Release Watcher Agent*",
            f"👤 Owner: `{self._escape(self.target_owner)}`",
            f"📦 Releases recentes \\(7 dias\\): *{len(releases)}*",
        ]
        for item in releases[:15]:
            lines.append(
                f"• [{self._escape(item['repo'])}]({item['url']}) - {self._escape(item['tag'])} \\| draft: {item['draft']} \\| pre: {item['prerelease']}"
            )

        self.github_client.send_telegram_msg("\n".join(lines), parse_mode="MarkdownV2")
        return {"agent": "release-watcher", "owner": self.target_owner, "releases": releases, "count": len(releases)}
