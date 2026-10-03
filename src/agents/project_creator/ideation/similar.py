"""Public-similarity search: how crowded is the space a candidate wants to enter?"""

from __future__ import annotations

from collections.abc import Callable
from itertools import islice
from typing import Any

Searcher = Callable[[list[str]], tuple[int, list[dict[str, Any]]]]


def make_searcher(github_client: Any, log: Callable[..., None], top: int = 3) -> Searcher:
    """Build a searcher returning (total public matches, top-N most starred matches)."""

    def search(terms: list[str]) -> tuple[int, list[dict[str, Any]]]:
        cleaned = [str(t).strip() for t in terms if str(t).strip()][:4]
        if not cleaned:
            return 0, []
        query = f"{' '.join(cleaned)} in:name,description,readme"
        try:
            results = github_client.g.search_repositories(query=query, sort="stars", order="desc")
            total = int(results.totalCount)
            found = [
                {"name": r.full_name, "stars": r.stargazers_count,
                 "description": (r.description or "")[:120]}
                for r in islice(results, top)
            ]
            return total, found
        except Exception as exc:
            log(f"Similar-repo search failed for {cleaned}: {exc}", "WARNING")
            return 0, []

    return search
