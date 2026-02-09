"""
PR Assistant Agent - Handles automated PR verification and merging.
This is a refactored version of the original Agent class.
"""
import re
import subprocess
import os
import tempfile
import shutil
from typing import Dict, Any
from datetime import datetime
from src.agents.base_agent import BaseAgent


class PRAssistantAgent(BaseAgent):
    """
    PR Assistant Agent

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
        target_owner: str = "juninmd",
        allowed_authors: list = None,
        **kwargs
    ):
        """
        Initialize PR Assistant Agent.

        Args:
            target_owner: GitHub username to monitor
            allowed_authors: List of trusted PR authors
        """
        super().__init__(*args, name="PRAssistant", **kwargs)
        self.target_owner = target_owner
        self.allowed_authors = allowed_authors or [
            "juninmd",
            "Copilot",
            "imgbot[bot]",
            "renovate[bot]",
            "dependabot[bot]",
            "Jules da Google"
        ]

    def _escape_telegram(self, text: str) -> str:
        """
        Escape special characters for Telegram MarkdownV2.
        For MarkdownV2, we need to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
        """
        if not text:
            return text
        special_chars = ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def run(self) -> Dict[str, Any]:
        """
        Execute PR Assistant workflow:
        1. Scan for open PRs across ALL repositories owned by target_owner
        2. Process each PR (check conflicts, pipeline)
        3. Auto-merge or request corrections

        Note: Unlike other agents, PR Assistant works on ALL repositories
        owned by target_owner, not limited to the allowlist.

        Returns:
            Summary of processed PRs
        """
        self.log("Starting PR Assistant workflow")
        self.log(f"Processing ALL repositories for user: {self.target_owner}")

        query = f"is:pr is:open user:{self.target_owner}"
        self.log(f"Scanning for PRs with query: {query}")

        results = {
            "total_found": 0,
            "merged": [],
            "conflicts_resolved": [],
            "pipeline_failures": [],
            "skipped": [],
            "draft_prs": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            issues = self.github_client.search_prs(query)
            results["total_found"] = issues.totalCount

            for issue in issues:
                repository = issue.repository.full_name
                self.log(f"Processing PR #{issue.number} in {repository}: {issue.title}")

                try:
                    pr = self.github_client.get_pr_from_issue(issue)

                    # Track draft PRs
                    if pr.draft:
                        results["draft_prs"].append({
                            "pr": pr.number,
                            "repository": repository,
                            "title": pr.title,
                            "url": pr.html_url,
                            "author": pr.user.login
                        })
                        self.log(f"PR #{pr.number} is draft, skipping auto-merge")
                        continue

                    pr_result = self.process_pr(pr)

                    # Add common info to all results
                    pr_result["repository"] = repository
                    pr_result["url"] = pr.html_url
                    if "title" not in pr_result:
                        pr_result["title"] = pr.title

                    # Categorize result
                    if pr_result.get("action") == "merged":
                        results["merged"].append(pr_result)
                    elif pr_result.get("action") == "conflicts_resolved":
                        results["conflicts_resolved"].append(pr_result)
                    elif pr_result.get("action") == "pipeline_failure":
                        results["pipeline_failures"].append(pr_result)
                    else:
                        results["skipped"].append(pr_result)

                except Exception as e:
                    self.log(f"Error processing PR #{issue.number}: {e}", "ERROR")
                    results["skipped"].append({
                        "pr": issue.number,
                        "repository": repository,
                        "title": issue.title,
                        "url": issue.html_url,
                        "error": str(e)
                    })

        except Exception as e:
            self.log(f"Error scanning PRs: {e}", "ERROR")
            return {"status": "error", "error": str(e)}

        self.log(f"Completed: {len(results['merged'])} merged, "
                f"{len(results['conflicts_resolved'])} conflicts resolved, "
                f"{len(results['pipeline_failures'])} pipeline issues")

        # Build Telegram Summary with categorized links
        # Use MarkdownV2 format with proper escaping
        # Limit items per category to avoid hitting Telegram's 4096 char limit
        MAX_ITEMS_PER_CATEGORY = 10

        summary_text = (
            "📊 *PR Assistant Summary*\n\n"
            f"🔍 *Total Analisados:* {results['total_found']}\n"
            f"✅ *Mergeados:* {len(results['merged'])}\n"
            f"🛠️ *Conflitos Resolvidos:* {len(results['conflicts_resolved'])}\n"
            f"❌ *Falhas de Pipeline:* {len(results['pipeline_failures'])}\n"
            f"📝 *Draft:* {len(results['draft_prs'])}\n"
            f"⏩ *Pulados/Pendentes:* {len(results['skipped'])}\n\n"
            f"👤 Dono: `{self._escape_telegram(self.target_owner)}`"
        )

        # Add merged PRs
        if results['merged']:
            summary_text += "\n\n✅ *PRs Mergeados:*\n"
            shown = 0
            for item in results['merged']:
                if shown >= MAX_ITEMS_PER_CATEGORY:
                    remaining = len(results['merged']) - shown
                    summary_text += f"\\.\\.\\. e mais {remaining} PRs\n"
                    break
                repo_short = item['repository'].split('/')[-1]
                title_short = item['title'][:45] + "..." if len(item['title']) > 45 else item['title']
                title_escaped = self._escape_telegram(title_short)
                summary_text += f"• [{self._escape_telegram(repo_short)}#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
                shown += 1

        # Add conflicts resolved
        if results['conflicts_resolved']:
            summary_text += "\n🛠️ *Conflitos Resolvidos:*\n"
            shown = 0
            for item in results['conflicts_resolved']:
                if shown >= MAX_ITEMS_PER_CATEGORY:
                    remaining = len(results['conflicts_resolved']) - shown
                    summary_text += f"\\.\\.\\. e mais {remaining} conflitos\n"
                    break
                repo_short = item['repository'].split('/')[-1]
                title_short = item.get('title', 'N/A')[:45]
                title_escaped = self._escape_telegram(title_short)
                if item.get('url'):
                    summary_text += f"• [{self._escape_telegram(repo_short)}#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
                else:
                    summary_text += f"• {self._escape_telegram(repo_short)}#{item['pr']} \\- {title_escaped}\n"
                shown += 1

        # Add pipeline failures
        if results['pipeline_failures']:
            summary_text += "\n❌ *Falhas de Pipeline:*\n"
            shown = 0
            for item in results['pipeline_failures']:
                if shown >= MAX_ITEMS_PER_CATEGORY:
                    remaining = len(results['pipeline_failures']) - shown
                    summary_text += f"\\.\\.\\. e mais {remaining} falhas\n"
                    break
                repo_short = item['repository'].split('/')[-1]
                title_short = item['title'][:45] + "..." if len(item['title']) > 45 else item['title']
                title_escaped = self._escape_telegram(title_short)
                summary_text += f"• [{self._escape_telegram(repo_short)}#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
                shown += 1

        # Add draft PRs
        if results['draft_prs']:
            summary_text += "\n📝 *PRs em Draft:*\n"
            shown = 0
            for item in results['draft_prs']:
                if shown >= MAX_ITEMS_PER_CATEGORY:
                    remaining = len(results['draft_prs']) - shown
                    summary_text += f"\\.\\.\\. e mais {remaining} drafts\n"
                    break
                repo_short = item['repository'].split('/')[-1]
                title_short = item['title'][:45] + "..." if len(item['title']) > 45 else item['title']
                title_escaped = self._escape_telegram(title_short)
                summary_text += f"• [{self._escape_telegram(repo_short)}#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
                shown += 1

        # Add skipped/pending PRs
        if results['skipped']:
            summary_text += "\n⏩ *Pulados/Pendentes:*\n"
            shown = 0
            for item in results['skipped']:
                if shown >= MAX_ITEMS_PER_CATEGORY:
                    remaining = len(results['skipped']) - shown
                    summary_text += f"\\.\\.\\. e mais {remaining} pulados\n"
                    break
                repo_short = item['repository'].split('/')[-1]
                title_short = item.get('title', 'N/A')[:45]
                reason = item.get('reason', 'unknown')
                title_escaped = self._escape_telegram(title_short)
                reason_escaped = self._escape_telegram(reason)
                if item.get('url'):
                    summary_text += f"• [{self._escape_telegram(repo_short)}#{item['pr']}]({item['url']}) \\- {title_escaped} \\({reason_escaped}\\)\n"
                else:
                    summary_text += f"• {self._escape_telegram(repo_short)}#{item['pr']} \\- {title_escaped} \\({reason_escaped}\\)\n"
                shown += 1

        self.github_client.send_telegram_msg(summary_text, parse_mode="MarkdownV2")

        return results

    def check_pipeline_status(self, pr) -> Dict[str, Any]:
        """
        Check if the PR pipeline is successful.
        Handles both legacy Statuses and modern CheckRuns.
        """
        try:
            commits = pr.get_commits()
            if commits.totalCount == 0:
                return {"success": False, "reason": "no_commits"}

            last_commit = commits.reversed[0]

            # 1. Combined Status (Legacy API)
            combined = last_commit.get_combined_status()
            if combined.state not in ['success', 'neutral'] and combined.total_count > 0:
                if combined.state in ['failure', 'error']:
                    failed_statuses = [s for s in combined.statuses if s.state in ['failure', 'error']]
                    if not failed_statuses:
                        details = f"Pipeline state is {combined.state}"
                    else:
                        details_list = [f"- {s.context}: {s.description}" for s in failed_statuses]
                        details = "Pipeline failed with status:\n" + "\n".join(details_list)
                    return {"success": False, "reason": "failure", "details": details}
                else:
                    return {"success": False, "reason": "pending", "details": f"Legacy status is {combined.state}"}

            # 2. Check Runs (Modern API)
            check_runs = last_commit.get_check_runs()
            failed_checks = []
            pending_checks = []
            for run in check_runs:
                if run.status != "completed":
                    pending_checks.append(run.name)
                elif run.conclusion not in ["success", "neutral", "skipped"]:
                    failed_checks.append(f"- {run.name}: {run.conclusion}")

            if failed_checks:
                details = "Pipeline failed with check runs:\n" + "\n".join(failed_checks)
                return {"success": False, "reason": "failure", "details": details}

            if pending_checks:
                return {"success": False, "reason": "pending", "details": f"Checks pending: {', '.join(pending_checks)}"}

            return {"success": True}
        except Exception as e:
            self.log(f"Error checking status for PR #{pr.number}: {e}", "ERROR")
            return {"success": False, "reason": "error", "details": str(e)}

    def process_pr(self, pr) -> Dict[str, Any]:
        """
        Process a single PR according to the rules.

        Args:
            pr: GitHub PR object
        """
        author = pr.user.login
        repo_name = pr.base.repo.full_name
        self.log(f"Analyzing PR #{pr.number} in {repo_name} (Author: {author}): {pr.title}")

        # Safety Check: Verify Author
        if author not in self.allowed_authors:
            self.log(f"Skipping PR #{pr.number} from author {author} (Not in allowlist)")
            return {
                "action": "skipped",
                "pr": pr.number,
                "reason": "unauthorized_author",
                "author": author
            }

        # Safety Check: Verify Author
        if pr.mergeable is False:
            self.log(f"PR #{pr.number} has conflicts")
            return self.handle_conflicts(pr)
        elif pr.mergeable is None:
             self.log(f"PR #{pr.number} mergeability unknown")
             return {"action": "skipped", "pr": pr.number, "reason": "mergeability_unknown"}

        # Check Pipeline Status
        status = self.check_pipeline_status(pr)
        if not status["success"]:
            reason = status["reason"]
            details = status.get("details", "")
            if reason == "failure":
                self.log(f"PR #{pr.number} has pipeline failures: {details}")
                self.handle_pipeline_failure(pr, details)
                return {"action": "pipeline_failure", "pr": pr.number, "reason": details}
            elif reason == "pending":
                self.log(f"PR #{pr.number} pipeline is pending: {details}")
                return {"action": "skipped", "pr": pr.number, "reason": f"pipeline_{reason}"}
            else:
                self.log(f"PR #{pr.number} status check error: {details}")
                return {"action": "skipped", "pr": pr.number, "reason": "status_error"}

        # Auto-Merge
        self.log(f"PR #{pr.number} is ready to merge (Pipeline and mergeability OK)")
        success, msg = self.github_client.merge_pr(pr)
        if not success:
            self.log(f"Failed to merge PR #{pr.number}: {msg}", "ERROR")
            return {"action": "merge_failed", "pr": pr.number, "error": msg}
        else:
            self.github_client.send_telegram_notification(pr)
            return {"action": "merged", "pr": pr.number, "title": pr.title}

    def handle_conflicts(self, pr):
        """Post a comment informing about merge conflicts."""
        try:
            # Check if we already commented about conflicts to avoid spam
            comments = self.github_client.get_issue_comments(pr)
            for comment in reversed(list(comments)):
                if "Existem conflitos no merge" in comment.body or "Merge conflicts detected" in comment.body:
                    self.log(f"PR #{pr.number} already has a conflict notification")
                    return {"action": "conflicts_resolved", "pr": pr.number, "title": pr.title}
        except Exception as e:
            self.log(f"Error checking existing comments for PR #{pr.number}: {e}", "ERROR")

        comment_body = (
            f"⚠️ **Conflitos de Merge Detectados**\n\n"
            f"Olá @{pr.user.login}, existem conflitos que impedem o merge automático deste PR.\n"
            f"Por favor, resolva os conflitos localmente ou via interface do GitHub para que eu possa processar o merge novamente."
        )

        try:
            pr.create_issue_comment(comment_body)
            self.log(f"Posted conflict notification on PR #{pr.number}")
        except Exception as e:
            self.log(f"Failed to post conflict notification for PR #{pr.number}: {e}", "ERROR")

        return {"action": "conflicts_resolved", "pr": pr.number, "title": pr.title}

    def handle_pipeline_failure(self, pr, failure_description):
        """Request corrections for pipeline failures."""
        try:
            comments = self.github_client.get_issue_comments(pr)
            for comment in reversed(list(comments)):
                if "Pipeline failed with status:" in comment.body or "❌ Pipeline Failure" in comment.body:
                    self.log(f"PR #{pr.number} already has a pipeline failure comment")
                    return
        except Exception as e:
            self.log(f"Error checking existing comments for PR #{pr.number}: {e}", "ERROR")

        # Generate static comment without AI
        comment = self._generate_pipeline_failure_comment(pr, failure_description)
        pr.create_issue_comment(comment)
        self.log(f"Posted pipeline failure comment on PR #{pr.number}")

    def _generate_pipeline_failure_comment(self, pr, failure_description: str) -> str:
        """Generate a pipeline failure comment using a template."""
        return (
            f"❌ **Pipeline Failure Detected**\n\n"
            f"Hi @{pr.user.login}, the CI/CD pipeline for this PR has failed.\n\n"
            f"**Failure Details:**\n"
            f"```\n{failure_description}\n```\n\n"
            f"Please review the errors above and push corrections to resolve these issues. "
            f"Once all checks pass, I'll be able to merge this PR automatically.\n\n"
            f"Thank you! 🙏"
        )
