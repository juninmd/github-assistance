"""
Interface Developer Agent - Specializes in UI/UX implementation using modern tools.
"""
from datetime import datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai import AIClient


class InterfaceDeveloperAgent(BaseAgent):
    """
    Interface Developer Agent

    Reads instructions from instructions.md file.
    """

    @property
    def persona(self) -> str:
        """Load persona from instructions.md"""
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        """Load mission from instructions.md"""
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_config: dict[str, Any] | None = None,
        target_owner: str = "juninmd",
        **kwargs,
    ):
        super().__init__(*args, name="interface_developer", **kwargs)
        self.target_owner = target_owner
        self.ai_provider = ai_provider or "ollama"
        self.ai_model = ai_model or "qwen3:1.7b"
        self.ai_config = ai_config or {}

    def _get_ai_client(self) -> AIClient | None:
        from src.ai import get_ai_client
        try:
            return get_ai_client(provider=self.ai_provider, model=self.ai_model, **self.ai_config)
        except Exception as exc:
            self.log(f"AI client unavailable: {exc}", "WARNING")
            return None

    def run(self) -> dict[str, Any]:
        """
        Execute the Interface Developer workflow:
        1. Check roadmaps for UI-related features
        2. Identify UI improvement opportunities
        3. Create GitHub issues for UI development suggestions
        """
        self.log("Starting Interface Developer workflow")

        repositories = self.get_allowed_repositories()
        if not repositories:
            self.log("No repositories in allowlist. Nothing to do.", "WARNING")
            return {"status": "skipped", "reason": "empty_allowlist"}

        results = {
            "ui_issues_created": [],
            "failed": [],
            "timestamp": datetime.now().isoformat()
        }

        for repo in repositories:
            try:
                self.log(f"Analyzing UI needs for: {repo}")
                ui_analysis = self.analyze_ui_needs(repo)

                if ui_analysis.get("has_ui_work"):
                    issue = self.create_ui_improvement_issue(repo, ui_analysis)
                    entry: dict[str, Any] = {
                        "repository": repo,
                        "issue_url": issue.get("issue_url") if issue else None,
                        "improvements": ui_analysis.get("improvements", []),
                    }
                    if issue and ui_analysis.get("improvements"):
                        improvements_text = "\n".join(f"- {imp}" for imp in ui_analysis["improvements"])
                        oc_result = self.run_opencode_on_repo(
                            repository=repo,
                            instructions=(
                                f"Implement the following UI/UX improvements in this repository:\n"
                                f"{improvements_text}\n\n"
                                f"Focus on changes that can be done without breaking existing functionality. "
                                f"Update DESIGN.md if it doesn't exist, add README badges if missing, "
                                f"and apply any straightforward styling improvements."
                            ),
                            title="ui: implement UI/UX improvements",
                        )
                        entry["opencode_pr_url"] = oc_result.get("pr_url")
                    results["ui_issues_created"].append(entry)
                else:
                    self.log(f"No UI work needed for {repo}")

            except Exception as e:
                self.log(f"Failed to process {repo}: {e}", "ERROR")
                results["failed"].append({
                    "repository": repo,
                    "error": str(e)
                })

        self.log(f"Completed: {len(results['ui_issues_created'])} UI issues created")
        self._send_summary(results)
        return results

    def _send_summary(self, results: dict) -> None:
        esc = self.telegram.escape_html
        issues = results.get("ui_issues_created", [])
        failed = results.get("failed", [])
        lines = [
            "🎨 <b>INTERFACE DEVELOPER</b>",
            "──────────────────────",
            f"🖼️ <b>Issues de UI criadas:</b> <code>{len(issues)}</code>",
            f"❌ <b>Falhas:</b> <code>{len(failed)}</code>",
        ]
        for item in issues[:5]:
            repo = esc(item["repository"])
            issue_url = item.get("issue_url", "")
            pr_url = item.get("opencode_pr_url", "")
            parts = []
            if issue_url:
                parts.append(f'<a href="{esc(issue_url)}">issue</a>')
            if pr_url:
                parts.append(f'<a href="{esc(pr_url)}">PR</a>')
            suffix = " → " + " | ".join(parts) if parts else ""
            lines.append(f"  └ {repo}{suffix}")
        self.telegram.send_message("\n".join(lines), parse_mode="HTML")

    def analyze_ui_needs(self, repository: str) -> dict[str, Any]:
        """
        Analyze repository for UI/UX improvement opportunities.
        """
        repo_info = self.get_repository_info(repository)
        if not repo_info:
            return {
                "has_ui_work": False,
                "improvements": []
            }

        language = repo_info.language
        has_frontend = language in ['JavaScript', 'TypeScript', 'Vue', 'HTML']

        issues = list(repo_info.get_issues(state='open'))[:30]
        ui_issues = [
            i for i in issues
            if any(keyword in i.title.lower() or keyword in (i.body or '').lower()
                   for keyword in ['ui', 'ux', 'design', 'interface', 'component', 'layout', 'style'])
        ]

        improvements = []
        if ui_issues:
            improvements.extend([f"Resolve UI issue: {issue.title}" for issue in ui_issues[:5]])

        try:
            repo_info.get_contents("DESIGN.md")
        except Exception:
            improvements.append("Create DESIGN.md with design system documentation")

        return {
            "has_ui_work": has_frontend and len(improvements) > 0,
            "improvements": improvements,
            "repo_obj": repo_info
        }

    def create_ui_improvement_issue(self, repository: str, analysis: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a GitHub issue for UI improvements.
        """
        repo_info = analysis.get("repo_obj")
        if not repo_info:
            return None

        improvements_text = "\n".join([f"- {imp}" for imp in analysis.get("improvements", [])])

        ai_client = self._get_ai_client()
        if ai_client:
            prompt = (
                f"Repository: {repository}\n"
                f"UI/UX improvement opportunities found:\n{improvements_text}\n\n"
                "Write a professional GitHub issue body that suggests these UI/UX improvements "
                "following modern web design best practices (vibrant colors, glassmorphism, responsive etc)."
            )
            try:
                body = ai_client.generate(prompt).strip()
            except Exception as exc:
                self.log(f"AI generation failed: {exc}", "WARNING")
                body = f"Proposed UI improvements:\n{improvements_text}"
        else:
            body = f"Proposed UI improvements:\n{improvements_text}"

        origin_footer = (
            "\n\n---\n"
            "🤖 **Origem Automatizada**\n"
            f"- **Agente:** `{self.name}`\n"
            f"- **Modelo:** `{self.ai_model}`\n"
            "- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)"
        )
        body = body + origin_footer

        try:
            issue = repo_info.create_issue(
                title="UI/UX Improvement Suggestions",
                body=body,
            )
            return {
                "repository": repository,
                "issue_number": issue.number,
                "issue_url": issue.html_url
            }
        except Exception as exc:
            self.log(f"Failed to create issue in {repository}: {exc}", "WARNING")
            return None
