"""
PR Assistant Agent - Handles automated PR verification and merging.
This is a refactored version of the original Agent class.
"""
import re
import subprocess
import os
import tempfile
import shutil
from typing import Dict, Any, Optional
from datetime import datetime
from src.agents.base_agent import BaseAgent
from src.ai_client import GeminiClient


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
        super().__init__(*args, name="pr_assistant", **kwargs)
        self.target_owner = target_owner
        self.allowed_authors = allowed_authors or [
            "juninmd",
            "Copilot",
            "imgbot[bot]",
            "renovate[bot]",
            "dependabot[bot]",
            "Jules da Google",
            "google-labs-jules"
        ]

        try:
            self.ai_client = GeminiClient()
        except Exception as e:
            self.log(f"Failed to initialize AI client: {e}", "WARNING")
            self.ai_client = None

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
                summary_text += f"• [{self._escape_telegram(repo_short)}\\#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
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
                    summary_text += f"• [{self._escape_telegram(repo_short)}\\#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
                else:
                    summary_text += f"• {self._escape_telegram(repo_short)}\\#{item['pr']} \\- {title_escaped}\n"
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
                summary_text += f"• [{self._escape_telegram(repo_short)}\\#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
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
                summary_text += f"• [{self._escape_telegram(repo_short)}\\#{item['pr']}]({item['url']}) \\- {title_escaped}\n"
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
                    summary_text += f"• [{self._escape_telegram(repo_short)}\\#{item['pr']}]({item['url']}) \\- {title_escaped} \\({reason_escaped}\\)\n"
                else:
                    summary_text += f"• {self._escape_telegram(repo_short)}\\#{item['pr']} \\- {title_escaped} \\({reason_escaped}\\)\n"
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

        # Safety Check: Verify Mergeability
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
        """
        Handle merge conflicts.
        If author is allowed, try to resolve autonomously.
        Otherwise, post a comment.
        """
        if pr.user.login in self.allowed_authors and self.ai_client:
            self.log(f"Author {pr.user.login} is trusted. Attempting autonomous conflict resolution.")
            return self.resolve_conflicts_autonomously(pr)

        # Fallback to comment
        return self.notify_conflicts(pr)

    def notify_conflicts(self, pr):
        """Post a comment informing about merge conflicts."""
        try:
            # Check if we already commented about conflicts to avoid spam
            comments = self.github_client.get_issue_comments(pr)
            for comment in reversed(list(comments)):
                if "Existem conflitos no merge" in comment.body or "Merge conflicts detected" in comment.body:
                    self.log(f"PR #{pr.number} already has a conflict notification")
                    return {"action": "conflicts_detected", "pr": pr.number, "title": pr.title}
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

        return {"action": "conflicts_detected", "pr": pr.number, "title": pr.title}

    def resolve_conflicts_autonomously(self, pr) -> Dict[str, Any]:
        """
        Resolve conflicts using AI.
        1. Clone repo
        2. Merge base into head
        3. Identify conflicts
        4. Use AI to resolve
        5. Push changes
        """
        repo_name = pr.head.repo.full_name
        base_branch = pr.base.ref
        head_branch = pr.head.ref
        clone_url = pr.head.repo.clone_url  # https://github.com/user/repo.git

        # Inject token for authentication
        token = self.github_client.token
        auth_url = clone_url.replace("https://", f"https://x-access-token:{token}@")

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = os.path.join(temp_dir, "repo")
            try:
                # 1. Clone
                self.log(f"Cloning {repo_name} to {repo_dir}")
                subprocess.run(
                    ["git", "clone", auth_url, repo_dir],
                    check=True,
                    capture_output=True
                )

                # Setup Git User
                subprocess.run(["git", "config", "user.email", "agent@juninmd.com"], cwd=repo_dir, check=True)
                subprocess.run(["git", "config", "user.name", "Jules da Google"], cwd=repo_dir, check=True)

                # 2. Checkout head branch
                self.log(f"Checking out {head_branch}")
                subprocess.run(["git", "checkout", head_branch], cwd=repo_dir, check=True, capture_output=True)

                # 3. Add base remote if needed (if fork)
                if pr.head.repo.id != pr.base.repo.id:
                    # It's a fork
                    base_url = pr.base.repo.clone_url.replace("https://", f"https://x-access-token:{token}@")
                    subprocess.run(["git", "remote", "add", "upstream", base_url], cwd=repo_dir, check=True)
                    subprocess.run(["git", "fetch", "upstream"], cwd=repo_dir, check=True)
                    merge_target = f"upstream/{base_branch}"
                else:
                    # Same repo
                    # Fetch origin to be sure
                    subprocess.run(["git", "fetch", "origin"], cwd=repo_dir, check=True)
                    merge_target = f"origin/{base_branch}"

                # 4. Try Merge
                self.log(f"Merging {merge_target} into {head_branch}")
                merge_result = subprocess.run(
                    ["git", "merge", merge_target],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True
                )

                if merge_result.returncode == 0:
                    self.log("Merge successful without conflicts (unexpected but good)")
                    subprocess.run(["git", "push"], cwd=repo_dir, check=True)
                    return {"action": "conflicts_resolved", "pr": pr.number, "title": pr.title}

                # 5. Handle Conflicts
                self.log("Merge failed with conflicts. Starting AI resolution...")

                # Get conflicted files
                diff_cmd = ["git", "diff", "--name-only", "--diff-filter=U"]
                conflicted_files = subprocess.check_output(diff_cmd, cwd=repo_dir, text=True).strip().split('\n')

                for file_path in conflicted_files:
                    if not file_path: continue
                    self.log(f"Resolving conflicts in {file_path}")
                    full_path = os.path.join(repo_dir, file_path)

                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    resolved_content = self._resolve_file_conflicts(content)

                    if resolved_content:
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(resolved_content)

                        subprocess.run(["git", "add", file_path], cwd=repo_dir, check=True)
                    else:
                        self.log(f"Failed to resolve {file_path}", "ERROR")
                        # Abort merge
                        subprocess.run(["git", "merge", "--abort"], cwd=repo_dir, check=False)
                        return {"action": "conflict_resolution_failed", "pr": pr.number, "error": f"Failed to resolve {file_path}"}

                # 6. Commit and Push
                self.log("All conflicts resolved. Committing and pushing...")
                subprocess.run(
                    ["git", "commit", "-m", "Merge branch 'main' into feature (Auto-resolved conflicts)"],
                    cwd=repo_dir,
                    check=True
                )
                subprocess.run(["git", "push"], cwd=repo_dir, check=True)

                self.log("Successfully pushed resolved conflicts")
                return {"action": "conflicts_resolved", "pr": pr.number, "title": pr.title}

            except subprocess.CalledProcessError as e:
                self.log(f"Git operation failed: {e}", "ERROR")
                if e.stderr:
                    self.log(f"Stderr: {e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else e.stderr}", "ERROR")
                return {"action": "conflict_resolution_failed", "pr": pr.number, "error": str(e)}
            except Exception as e:
                self.log(f"Error during conflict resolution: {e}", "ERROR")
                return {"action": "conflict_resolution_failed", "pr": pr.number, "error": str(e)}

    def _resolve_file_conflicts(self, content: str) -> Optional[str]:
        """
        Parse file content, find conflict blocks, resolve them using AI.
        """
        # Regex to find conflict blocks: <<<<<<< ... ======= ... >>>>>>>
        # We use DOTALL to match newlines
        # Pattern captures: start marker, content, separator, content, end marker + branch name + optional newline
        pattern = re.compile(r'(<<<<<<<.*?=======(?:.*?)>>>>>>>.*?\n?)', re.DOTALL)

        parts = []
        last_pos = 0

        matches = list(pattern.finditer(content))
        if not matches:
             self.log("No conflict markers found despite git reporting conflict", "WARNING")
             return None

        for match in matches:
            # Add non-conflicting part before this match
            parts.append(content[last_pos:match.start()])

            conflict_block = match.group(1)
            # Call AI
            # Here content is the WHOLE file content.
            resolved_block = self.ai_client.resolve_conflict(content, conflict_block)

            # Sanity check: ensure no conflict markers remain in resolved block
            if '<<<<<<<' in resolved_block or '=======' in resolved_block or '>>>>>>>' in resolved_block:
                self.log("AI failed to remove conflict markers completely.", "WARNING")
                # Fallback: keep original block? Or fail?
                # If we fail, we abort the whole PR resolution.
                # Let's try to strip markers if simple enough, otherwise return None to fail.
                # Actually, sometimes AI might return a block with markers if it thinks it should.
                # But we asked it to return ONLY resolved code.
                # If we return None, the whole process fails.
                return None

            parts.append(resolved_block)
            last_pos = match.end()

        # Add remaining part
        parts.append(content[last_pos:])

        return "".join(parts)

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

        # Generate comment
        if self.ai_client:
            try:
                comment = self.ai_client.generate_pr_comment(failure_description)
            except Exception as e:
                self.log(f"AI comment generation failed: {e}", "ERROR")
                comment = self._generate_pipeline_failure_comment(pr, failure_description)
        else:
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
