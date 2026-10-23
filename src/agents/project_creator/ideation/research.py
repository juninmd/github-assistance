"""Market research for a chosen candidate: competing repos on GitHub plus web search hits."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from typing import Any

import requests

MAX_COMPETITORS = 5
README_CHARS = 1800
_DDG_URL = "https://html.duckduckgo.com/html/"
_DDG_RESULT = re.compile(
    r'class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG.sub("", text)).strip()


class MarketResearcher:
    def __init__(self, github: Any, log: Callable[..., None], http_get: Callable[..., Any] | None = None):
        self._github, self._log = github, log
        self._get = http_get or requests.get

    def research(self, queries: list[str], owner: str) -> dict[str, list[dict[str, Any]]]:
        """Return {'competitors': [...], 'web': [...]}; every source fails soft."""
        queries = [q for q in queries if isinstance(q, str) and q.strip()][:3]
        return {
            "competitors": self._github_competitors(queries, owner.lower()),
            "web": self._web(queries),
        }

    def _github_competitors(self, queries: list[str], owner: str) -> list[dict[str, Any]]:
        found: dict[str, Any] = {}
        for query in queries:
            try:
                hits = self._github.search_repositories(query=f"{query} in:name,description,readme fork:false", sort="stars", order="desc")
                for repo in list(hits[:MAX_COMPETITORS]):
                    if repo.full_name.split("/")[0].lower() != owner:
                        found.setdefault(repo.full_name, repo)
            except Exception as exc:
                self._log(f"GitHub competitor search failed for '{query}': {exc}", "WARNING")
        ranked = sorted(found.values(), key=lambda r: getattr(r, "stargazers_count", 0), reverse=True)
        return [self._summarize(repo) for repo in ranked[:MAX_COMPETITORS]]

    def _summarize(self, repo: Any) -> dict[str, Any]:
        readme, files = "", []
        try:
            readme = repo.get_readme().decoded_content.decode("utf-8", "replace")[:README_CHARS]
        except Exception as exc:
            self._log(f"No README for {repo.full_name}: {exc}", "DEBUG")
        try:
            files = [c.path for c in repo.get_contents("")][:25]
        except Exception as exc:
            self._log(f"No file listing for {repo.full_name}: {exc}", "DEBUG")
        return {
            "name": repo.full_name,
            "url": repo.html_url,
            "stars": getattr(repo, "stargazers_count", 0),
            "language": getattr(repo, "language", None),
            "description": getattr(repo, "description", None) or "",
            "root_files": files,
            "readme_excerpt": readme,
        }

    def _web(self, queries: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for query in queries[:2]:
            try:
                resp = self._get(_DDG_URL, params={"q": query}, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                resp.raise_for_status()
                for m in list(_DDG_RESULT.finditer(resp.text))[:5]:
                    results.append(
                        {"title": _clean(m["title"]), "url": html.unescape(m["url"]), "snippet": _clean(m["snippet"])}
                    )
            except Exception as exc:
                self._log(f"Web search failed for '{query}': {exc}", "WARNING")
        return results[:8]


def format_research(research: dict[str, list[dict[str, Any]]]) -> str:
    """Compact text block for prompts."""
    lines = []
    for c in research.get("competitors", []):
        lines.append(
            f"- {c['name']} ({c['stars']}★, {c.get('language') or 'n/a'}) {c['url']}\n"
            f"  {c['description']}\n  files: {', '.join(c['root_files'][:15])}\n"
            f"  README: {c['readme_excerpt'][:900].replace(chr(10), ' ')}"
        )
    for w in research.get("web", []):
        lines.append(f"- [web] {w['title']} {w['url']} — {w['snippet']}")
    return "\n".join(lines) or "none found"
