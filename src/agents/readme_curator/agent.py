"""Readme Curator Agent - Refreshes missing, stale (>6 months) or weak READMEs via opencode PRs."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from github.GithubException import UnknownObjectException
from github.Repository import Repository

from src.agents.base_agent import BaseAgent
from src.agents.readme_curator.scoring import DEFAULT_MIN_SCORE, score_readme

DEFAULT_MAX_AGE_DAYS = 180


class ReadmeCuratorAgent(BaseAgent):
    """
    Scans every repository of the target owner and refreshes README files that are
    missing, older than ``README_MAX_AGE_DAYS`` (default 180) or below the quality bar.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, name="readme_curator", enforce_repository_allowlist=False, **kwargs
        )
        self._readme_dates: dict[str, datetime] = {}

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        """Execute the README curation workflow on all repositories of the target owner."""
        self.check_rate_limit()
        self.log("Starting Readme Curator workflow")
        results: dict[str, Any] = {"processed": [], "skipped": [], "failed": []}

        repos = []
        for repo_name in self.get_allowed_repositories():
            try:
                repo = self.github_client.get_repo(repo_name)
                repos.append((self._readme_last_modified(repo), repo))
            except Exception as e:
                self.log(f"Failed to process {repo_name}: {e}", "ERROR")
                results["failed"].append({"repository": repo_name, "error": str(e)})

        # Oldest README first (missing ones lead), so every repo ends up refreshed.
        repos.sort(key=lambda item: item[0])
        for _, repo in repos:
            try:
                self._process_repository(repo, results)
            except Exception as e:
                self.log(f"Failed to process {repo.full_name}: {e}", "ERROR")
                results["failed"].append({"repository": repo.full_name, "error": str(e)})

        self._send_summary(results)
        return results

    def _process_repository(self, repo: Repository, results: dict[str, Any]) -> None:
        repo_name = repo.full_name
        if getattr(repo, "archived", False) or getattr(repo, "fork", False):
            results["skipped"].append({"repository": repo_name, "reason": "archived_or_fork"})
            return
        self.log(f"Checking README quality for {repo_name}")

        try:
            readme_file = repo.get_readme()
            content = readme_file.decoded_content.decode("utf-8")
            needs_improvement, reason = self._readme_needs_improvement(content)
            if not needs_improvement:
                needs_improvement, reason = self._readme_is_stale(repo)
        except UnknownObjectException:
            content = ""
            needs_improvement = True
            reason = "missing"
        except Exception as e:
            self.log(f"Error checking README in {repo_name}: {e}", "WARNING")
            needs_improvement = True
            reason = f"error: {type(e).__name__}"

        if not needs_improvement:
            self.log(f"README for {repo_name} is already high-quality.")
            results["skipped"].append({"repository": repo_name, "reason": "already_good"})
            return

        self.log(f"README in {repo_name} needs improvement because it is {reason}")

        instructions = (
            f"Repository: {repo_name}\n"
            f"Task: Create or significantly improve README.md (current state: {reason}).\n\n"
            "Mandatory rubric - make sure ALL items are covered:\n"
            "- Write the README in English, translating any existing content in another language.\n"
            "- Title (H1) + short description of what the project does and who it is for (pitch).\n"
            "- Real badges (CI, coverage, version/license) pointing to the correct repo URLs.\n"
            "- Installation using the package manager detected in the repository.\n"
            "- Copy-pasteable quickstart (code blocks) with an example that actually works.\n"
            "- Configuration table (environment variables / options), when applicable.\n"
            "- A Mermaid diagram (architecture/flow) and, if possible, a screenshot/GIF.\n"
            "- Sections: Features, Usage, Configuration, Contributing, License.\n"
            "- Verify every statement against the current code; fix outdated commands, paths and versions.\n"
            "- Preserve valid badges, links and footers; expand, do not discard valid content.\n"
            "- No generic AI filler ('High Performance', 'Clean Architecture') without evidence.\n"
            "- In the PR body, include a preview (rendered summary / before-and-after).\n"
            "- Finally, commit/push to a branch and open a pull request."
        )

        title = f"Improve README.md for {repo.name}"
        oc_result = self.create_opencode_task(
            repository=repo_name,
            instructions=instructions,
            title=title,
            base_branch=repo.default_branch,
        )

        results["processed"].append({
            "repository": repo_name,
            "reason": reason,
            "pr_url": oc_result.get("task_url"),
            "status": oc_result.get("status"),
        })

    def _readme_needs_improvement(self, content: str | None) -> tuple[bool, str]:
        score = score_readme(content)
        min_score = self._min_score()
        if score.needs_work(min_score):
            missing = ", ".join(score.missing) or "geral"
            return True, f"score {score.score}/{min_score} (faltando: {missing})"
        return False, ""

    def _readme_last_modified(self, repo: Repository) -> datetime:
        """Date of the last commit touching the README; ``min`` if missing, ``max`` if unknown."""
        name = repo.full_name
        if name in self._readme_dates:
            return self._readme_dates[name]
        if getattr(repo, "archived", False) or getattr(repo, "fork", False):
            return datetime.max.replace(tzinfo=UTC)
        try:
            path = repo.get_readme().path
            last = repo.get_commits(path=path)[0].commit.committer.date
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
        except UnknownObjectException:
            last = datetime.min.replace(tzinfo=UTC)
        except Exception as e:
            self.log(f"Could not read README history for {name}: {e}", "WARNING")
            last = datetime.max.replace(tzinfo=UTC)
        self._readme_dates[name] = last
        return last

    def _readme_is_stale(self, repo: Repository) -> tuple[bool, str]:
        """True when the last commit touching the README is older than the max age."""
        max_age = self._max_age_days()
        age = datetime.now(UTC) - self._readme_last_modified(repo)
        if age > timedelta(days=max_age):
            return True, f"stale (last updated {age.days} days ago, limit {max_age})"
        return False, ""

    @staticmethod
    def _max_age_days() -> int:
        try:
            return int(os.getenv("README_MAX_AGE_DAYS", "") or DEFAULT_MAX_AGE_DAYS)
        except ValueError:
            return DEFAULT_MAX_AGE_DAYS

    @staticmethod
    def _min_score() -> int:
        try:
            return int(os.getenv("README_MIN_SCORE", "") or DEFAULT_MIN_SCORE)
        except ValueError:
            return DEFAULT_MIN_SCORE

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        processed = results.get("processed", [])
        skipped = results.get("skipped", [])
        failed = results.get("failed", [])
        lines = [
            "📚 <b>README CURATOR AGENT</b>",
            "──────────────────────",
            f"✅ <b>Atualizados (PRs abertos):</b> <code>{len(processed)}</code>",
            f"skip <b>Pulados:</b> <code>{len(skipped)}</code>  ❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for item in processed[:5]:
            repo = item["repository"]
            pr_url = item.get("pr_url")
            reason = item.get("reason", "unknown")
            if pr_url:
                lines.append(f'  └ <a href="{esc(pr_url)}">{esc(repo)}</a> ({esc(reason)})')
            else:
                lines.append(f'  └ <code>{esc(repo)}</code> ({esc(reason)})')
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")
