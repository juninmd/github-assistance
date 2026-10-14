"""Apply review suggestions from trusted bot reviewers to a PR branch."""

from __future__ import annotations

import re
from collections import defaultdict

from github import GithubException

_SUGGESTION_RE = re.compile(r"```suggestion[^\r\n]*\r?\n(.*?)\r?\n```", re.DOTALL)


def normalize_login(login: str | None) -> str:
    normalized = (login or "").strip().lower()
    if normalized.endswith("[bot]"):
        normalized = normalized[:-5]
    return normalized


def _extract_suggestion_indices(line: int, start_line: int | None) -> tuple[int, int]:
    if isinstance(start_line, int) and start_line > 0:
        start = min(start_line, line)
        end = max(start_line, line)
        return start - 1, end
    return line - 1, line


def _parse_suggestion_from_comment(comment) -> list[dict]:
    pattern = r'```suggestion[^\r\n]*\r?\n(.*?)\r?\n```'
    suggestions = re.findall(pattern, comment.body or "", re.DOTALL)
    file_path = comment.path
    line = getattr(comment, "line", None)
    start_line = getattr(comment, "start_line", None)
    if not isinstance(line, int) or line <= 0:
        return []
    start_idx, end_idx = _extract_suggestion_indices(line, start_line)
    return [
        {
            "start_idx": start_idx,
            "end_idx": end_idx,
            "suggestion": s,
            "author": comment.user.login,
            "file_path": file_path,
        }
        for s in suggestions
    ]


def _collect_suggestions_from_reviews(
    review_comments: list, normalized_bots: set[str]
) -> dict[str, list[dict]]:
    file_suggestions: dict[str, list[dict]] = defaultdict(list)
    for comment in review_comments:
        comment_login = normalize_login(getattr(comment.user, "login", ""))
        if comment_login not in normalized_bots:
            continue
        for parsed in _parse_suggestion_from_comment(comment):
            fp = parsed.pop("file_path")
            file_suggestions[fp].append(parsed)
    return file_suggestions


def _apply_file_suggestions(repo, branch_ref: str, file_path: str, suggestions: list[dict]) -> int:
    file_content = repo.get_contents(file_path, ref=branch_ref)
    lines = file_content.decoded_content.decode("utf-8").splitlines()
    suggestions.sort(key=lambda x: x["start_idx"], reverse=True)
    authors: set[str] = set()
    for sugg in suggestions:
        suggestion_lines = sugg["suggestion"].split("\n")
        lines = lines[: sugg["start_idx"]] + suggestion_lines + lines[sugg["end_idx"] :]
        authors.add(sugg["author"])
    new_content = "\n".join(lines)
    author_list = ", ".join(authors)
    co_authors = "\n".join(
        f"Co-authored-by: {a} <{a}@users.noreply.github.com>" for a in authors
    )
    repo.update_file(
        file_path,
        f"Apply suggestion from {author_list}\n\n{co_authors}\n",
        new_content,
        file_content.sha,
        branch=branch_ref,
    )
    return len(suggestions)


def accept_review_suggestions(
    github_client, pr, bot_usernames: list[str]
) -> tuple[bool, str, int]:
    try:
        normalized_bots = {
            normalize_login(username)
            for username in bot_usernames
            if isinstance(username, str) and username.strip()
        }
        try:
            review_comments = list(pr.get_review_comments())
        except GithubException as e:
            return False, f"Failed to fetch review comments: {e.status} {e.data}", 0

        file_suggestions = _collect_suggestions_from_reviews(review_comments, normalized_bots)
        if not file_suggestions:
            return True, "No suggestions found to apply", 0

        repo = pr.head.repo
        suggestions_applied = 0
        for file_path, suggestions in file_suggestions.items():
            try:
                suggestions_applied += _apply_file_suggestions(repo, pr.head.ref, file_path, suggestions)
            except Exception as e:
                print(f"Error applying suggestion(s) to {file_path}: {e}")

        if suggestions_applied > 0:
            return True, f"Applied {suggestions_applied} suggestion(s)", suggestions_applied
        return True, "No suggestions found to apply", 0
    except Exception as e:
        return False, f"Error processing review suggestions: {e}", 0
