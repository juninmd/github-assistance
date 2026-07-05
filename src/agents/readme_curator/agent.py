"""Readme Curator Agent - Identifies poor/short READMEs and uses opencode to improve them."""

from typing import Any

from github.GithubException import UnknownObjectException
from github.Repository import Repository

from src.agents.base_agent import BaseAgent


class ReadmeCuratorAgent(BaseAgent):
    """
    Analyzes allowed repositories and improves missing or low-quality README files.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, name="readme_curator", enforce_repository_allowlist=True, **kwargs
        )

    @property
    def persona(self) -> str:
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        return self.get_instructions_section("## Mission")

    def run(self) -> dict[str, Any]:
        """Execute the README curation workflow on allowed repositories."""
        self.check_rate_limit()
        self.log("Starting Readme Curator workflow")
        results: dict[str, Any] = {"processed": [], "skipped": [], "failed": []}

        for repo_name in self.get_allowed_repositories():
            try:
                repo = self.github_client.get_repo(repo_name)
                self._process_repository(repo, results)
            except Exception as e:
                self.log(f"Failed to process {repo_name}: {e}", "ERROR")
                results["failed"].append({"repository": repo_name, "error": str(e)})

        self._send_summary(results)
        return results

    def _process_repository(self, repo: Repository, results: dict[str, Any]) -> None:
        repo_name = repo.full_name
        self.log(f"Checking README quality for {repo_name}")

        try:
            readme_file = repo.get_readme()
            content = readme_file.decoded_content.decode("utf-8")
            needs_improvement, reason = self._readme_needs_improvement(content)
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
            f"Task: Create or significantly improve the main README.md file (current state: {reason}).\n\n"
            "Requirements:\n"
            "- It must be written in clear, structured Markdown.\n"
            "- Must contain: Project Title, Description, Prerequisites / Installation instructions, Usage guide with clear examples, Configuration settings (if any), and License details.\n"
            "- Ensure the style is professional and informative, fitting for high-quality engineering standards.\n"
            "- Keep any existing relevant content and expand upon it.\n"
            "- Once updated, commit/push to a new branch and open a pull request."
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
        if not content or not content.strip():
            return True, "empty"

        if len(content) < 300:
            return True, "too_short"

        # Check for headers count
        headers = [line for line in content.splitlines() if line.strip().startswith("#")]
        if len(headers) < 2:
            return True, "insufficient_sections"

        # Check for critical documentation keywords
        keywords = ["install", "usage", "setup", "config", "exempl", "run", "instalac", "uso", "como usar", "dependenc"]
        content_lower = content.lower()
        found_keywords = [kw for kw in keywords if kw in content_lower]
        if len(found_keywords) < 2:
            return True, "missing_key_details"

        return False, ""

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
