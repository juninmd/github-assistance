"""
PR Assistant Agent - Handles automated PR verification and merging.
This is a refactored version of the original Agent class.
"""
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from typing import Any

from src.agents.base_agent import BaseAgent
from src.ai_client import get_ai_client


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
        ai_provider: str = "gemini",
        ai_model: str = "gemini-2.5-flash",
        ai_config: dict[str, Any] = None,
        **kwargs
    ):
        """
        Initialize PR Assistant Agent.

        Args:
            target_owner: GitHub username to monitor
            allowed_authors: List of trusted PR authors
            ai_provider: AI provider to use
            ai_model: AI model to use
            ai_config: Additional AI configuration
        """
        super().__init__(*args, name="pr_assistant", **kwargs)
        self.target_owner = target_owner
        self.allowed_authors = allowed_authors or [
            "juninmd",
            "Copilot",
            "Copilot[bot]",
            "imgbot[bot]",
            "renovate[bot]",
            "dependabot[bot]",
            "Jules da Google",
            "google-labs-jules",
            "google-labs-jules[bot]",
            "gemini-code-assist",
            "gemini-code-assist[bot]",
        ]

        # Google bot usernames for auto-accepting suggestions
        self.google_bot_usernames = ["Jules da Google", "google-labs-jules", "gemini-code-assist"]

        # Minimum PR age in minutes before auto-merge
        self.min_pr_age_minutes = 10

        # Initialize AI Client for autonomous operations
        ai_config = ai_config or {}
        ai_config["model"] = ai_model

        self.ai_client = get_ai_client(ai_provider, **ai_config)


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

    def get_pr_age_minutes(self, pr) -> float:
        """
        Calculate PR age in minutes.

        Args:
            pr: GitHub PR object

        Returns:
            Age of PR in minutes
        """
        now = datetime.now(UTC)
        pr_created = pr.created_at

        # Ensure pr_created is timezone-aware
        if pr_created.tzinfo is None:
            pr_created = pr_created.replace(tzinfo=UTC)

        return (now - pr_created).total_seconds() / 60

    def is_pr_too_young(self, pr) -> bool:
        """
        Check if PR was created less than min_pr_age_minutes ago.

        Args:
            pr: GitHub PR object

        Returns:
            True if PR is too young to merge, False otherwise
        """
        return self.get_pr_age_minutes(pr) < self.min_pr_age_minutes

    def run(self, specific_pr: str | None = None) -> dict[str, Any]:
        """
        Execute PR Assistant workflow:
        1. Scan for open PRs or get a specific PR
        2. Process each PR (check conflicts, pipeline)
        3. Auto-merge or request corrections

        Args:
            specific_pr: Optional PR reference in format 'owner/repo#number' or just 'number' (for current owner)

        Returns:
            Summary of processed PRs
        """
        self.log(f"Starting PR Assistant workflow{f' for {specific_pr}' if specific_pr else ''}")

        results = {
            "total_found": 0,
            "merged": [],
            "conflicts_resolved": [],
            "pipeline_failures": [],
            "skipped": [],
            "draft_prs": [],
            "suggestions_applied": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            prs_to_process = self._get_prs_to_process(specific_pr)
            results["total_found"] = len(prs_to_process)

            for pr_info in prs_to_process:
                repository = pr_info["repository"]
                number = pr_info["number"]
                self.log(f"Processing PR #{number} in {repository}")

                try:
                    # If we don't have the pr object yet, fetch it
                    pr = pr_info.get("pr_obj")
                    if not pr:
                        pr = self.github_client.get_pr(repository, number)

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
                    self.log(f"Error processing PR #{number} in {repository}: {e}", "ERROR")  # pragma: no cover
                    results["skipped"].append({
                        "pr": number,
                        "repository": repository,
                        "reason": f"error: {str(e)}"
                    })  # pragma: no cover

        except Exception as e:
            self.log(f"Error scanning PRs: {e}", "ERROR")  # pragma: no cover
            return {"status": "error", "error": str(e)}  # pragma: no cover

        self.log(f"Completed: {len(results['merged'])} merged, "
                f"{len(results['conflicts_resolved'])} conflicts resolved, "
                f"{len(results['pipeline_failures'])} pipeline issues")

        # Build Telegram Summary
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

    def _get_prs_to_process(self, specific_pr: str | None = None) -> list[dict[str, Any]]:
        """
        Get list of PRs to process.
        Returns a list of dicts with 'repository', 'number' and optionally 'pr_obj'.
        """
        if specific_pr:
            # Handle format 'owner/repo#number' or 'repo#number' or 'number'
            if '#' in specific_pr:
                repo_ref, number_str = specific_pr.split('#')
                if '/' not in repo_ref:
                    repository = f"{self.target_owner}/{repo_ref}"
                else:
                    repository = repo_ref
                number = int(number_str)
            else:
                # If just a number, assume it's in a repository with the same name as target_owner (default behavior)
                # Or we search for this PR number across all owned repos (less efficient)
                number = int(specific_pr)
                # For simplicity, we search for this PR number in the owner's repos
                query = f"is:pr is:open user:{self.target_owner} {number}"
                self.log(f"Searching for PR #{number} with query: {query}")
                issues = self.github_client.search_prs(query)
                return [{"repository": issue.repository.full_name, "number": issue.number, "pr_obj": self.github_client.get_pr_from_issue(issue)} for issue in issues if issue.number == number]

            return [{"repository": repository, "number": number}]

        # Default: scan all open PRs
        self.log(f"Processing ALL repositories for user: {self.target_owner}")
        query = f"is:pr is:open user:{self.target_owner}"
        self.log(f"Scanning for PRs with query: {query}")

        issues = self.github_client.search_prs(query)
        return [{"repository": issue.repository.full_name, "number": issue.number, "pr_obj": self.github_client.get_pr_from_issue(issue)} for issue in issues]

    def check_pipeline_status(self, pr) -> dict[str, Any]:
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
                if combined.state in ['failure', 'error', 'pending']:
                    # Check for billing/limit errors specifically
                    billing_errors = [s for s in combined.statuses if s.state in ['failure', 'error'] and ('account payments' in (s.description or '') or 'spending limit' in (s.description or ''))]

                    netlify_errors = [s for s in combined.statuses if s.state in ['failure', 'error'] and ('netlify' in (s.context or ''))]

                    if netlify_errors:
                        details_list = [f"- {s.context}: {s.description}" for s in netlify_errors]
                        details = "Pipeline failed due to netlify issues:\n" + "\n".join(details_list)
                        return {"success": True, "reason": "failure", "details": details}

                    if billing_errors:
                        details_list = [f"- {s.context}: {s.description}" for s in billing_errors]
                        details = "Pipeline failed due to billing/limit issues:\n" + "\n".join(details_list)
                        return {"success": True, "reason": "failure", "details": details}

                    # Check for other failures
                    failed_statuses = [s for s in combined.statuses if s.state in ['failure', 'error']]
                    if failed_statuses:
                        details_list = [f"- {s.context}: {s.description}" for s in failed_statuses]
                        details = "Pipeline failed with status:\n" + "\n".join(details_list)
                        return {"success": False, "reason": "failure", "details": details}

                    if combined.state == 'pending':
                         return {"success": False, "reason": "pending", "details": "Legacy status is pending"}
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
                    failure_msg = f"- {run.name}: {run.conclusion}"

                    # Try to get more details from output
                    details = []
                    if run.output:
                        if run.output.title:
                            details.append(run.output.title)
                        if run.output.summary:
                            details.append(run.output.summary)

                    # Get annotations if any (often contains the actual error for failed jobs)
                    is_soft_failure = False
                    try:
                        annotations = run.get_annotations()
                        for ann in annotations:
                            if ann.message:
                                details.append(ann.message)
                                lower_msg = ann.message.lower()
                                if "billing" in lower_msg or "netlify" in lower_msg:
                                    is_soft_failure = True
                    except Exception as e:
                        self.log(f"Error fetching annotations for {run.name}: {e}", "WARNING")

                    if is_soft_failure:
                        continue  # Skip this failure as it's a soft failure

                    if details:
                        failure_msg += f" ({'; '.join(details)})"

                    failed_checks.append(failure_msg)

            if failed_checks:
                details = "Pipeline failed with check runs:\n" + "\n".join(failed_checks)
                return {"success": False, "reason": "failure", "details": details}

            if pending_checks:
                return {"success": False, "reason": "pending", "details": f"Checks pending: {', '.join(pending_checks)}"}

            return {"success": True}
        except Exception as e:
            self.log(f"Error checking status for PR #{pr.number}: {e}", "ERROR")  # pragma: no cover
            return {"success": False, "reason": "error", "details": str(e)}  # pragma: no cover

    def process_pr(self, pr) -> dict[str, Any]:
        """
        Process a single PR according to the rules.

        Args:
            pr: GitHub PR object
        """
        author = pr.user.login
        repo_name = pr.base.repo.full_name
        self.log(f"Analyzing PR #{pr.number} in {repo_name} (Author: {author}): {pr.title}")

        has_commit_suggestion = self._has_commit_suggestion_in_pr_message(pr)

        # Safety Check: Verify Author
        if author not in self.allowed_authors:
            if has_commit_suggestion:
                rejection_comment = (
                    "❌ Detectei uma sugestão de commit na mensagem deste PR, "
                    "mas ela será rejeitada porque o autor não está na lista de usuários confiáveis."
                )
                try:
                    self.github_client.comment_on_pr(pr, rejection_comment)
                except Exception as e:
                    self.log(f"Failed to comment rejection on PR #{pr.number}: {e}", "WARNING")

            self.log(f"Skipping PR #{pr.number} from author {author} (Not in allowlist)")
            return {
                "action": "skipped",
                "pr": pr.number,
                "reason": "unauthorized_author",
                "author": author
            }

        if has_commit_suggestion:
            acceptance_comment = (
                "✅ Detectei uma sugestão de commit na mensagem deste PR e ela foi "
                "aceita automaticamente porque o autor está na lista de confiança."
            )
            try:
                self.github_client.comment_on_pr(pr, acceptance_comment)
            except Exception as e:
                self.log(f"Failed to comment acceptance on PR #{pr.number}: {e}", "WARNING")

        # Check PR Age: Skip if created less than 10 minutes ago
        if self.is_pr_too_young(pr):
            age_minutes = self.get_pr_age_minutes(pr)
            self.log(f"PR #{pr.number} is too young ({age_minutes:.1f} minutes old, minimum {self.min_pr_age_minutes} minutes)")
            return {
                "action": "skipped",
                "pr": pr.number,
                "reason": f"pr_too_young_{age_minutes:.1f}min",
                "title": pr.title
            }

        # Check and Apply Google Bot Review Suggestions
        success, msg, suggestions_count = self.github_client.accept_review_suggestions(pr, self.google_bot_usernames)
        if suggestions_count > 0:
            self.log(f"Applied {suggestions_count} review suggestion(s) from Google bot on PR #{pr.number}")
            try:
                pr.create_issue_comment(f"✅ Apliquei automaticamente {suggestions_count} sugestão(ões) de code review.")
            except Exception as e:
                self.log(f"Failed to comment on PR #{pr.number} after applying suggestions: {e}", "WARNING")
        elif not success:
            self.log(f"Error applying review suggestions on PR #{pr.number}: {msg}", "WARNING")

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
            add_label = getattr(self.github_client, "add_label_to_pr", None)
            if callable(add_label):
                label_result = add_label(pr, "auto-merge")
                label_success, label_msg = (label_result if isinstance(label_result, tuple) else (True, "ok"))
                if not label_success:
                    self.log(f"Failed to add 'auto-merge' label to PR #{pr.number}: {label_msg}", "WARNING")

            merge_comment = "✅ Este PR foi mergeado automaticamente pelo PR Assistant."
            try:
                self.github_client.comment_on_pr(pr, merge_comment)
            except Exception as e:
                self.log(f"Failed to comment on PR #{pr.number} after merge: {e}", "WARNING")

            self.github_client.send_telegram_notification(pr)
            return {"action": "merged", "pr": pr.number, "title": pr.title}

    def _has_commit_suggestion_in_pr_message(self, pr) -> bool:
        """Return True when PR body contains a commit suggestion marker."""
        raw_body = getattr(pr, "body", "")
        if not isinstance(raw_body, str):
            return False

        body = raw_body.lower()
        if not body:
            return False

        patterns = [
            r"commit\s+suggestion",
            r"sugest[aã]o\s+de\s+commit",
            r"```suggestion",
        ]
        return any(re.search(pattern, body, re.IGNORECASE) for pattern in patterns)

    def handle_conflicts(self, pr):
        """
        Handle merge conflicts.
        If author is allowed, try to resolve autonomously.
        Otherwise, post a comment.
        """
        # Try autonomous resolution if allowed
        if pr.user.login in self.allowed_authors:
            self.log(f"Attempting autonomous conflict resolution for PR #{pr.number}")
            success = self.resolve_conflicts_autonomously(pr)
            if success:
                self.log(f"Autonomous conflict resolution successful for PR #{pr.number}")
                return {"action": "conflicts_resolved", "pr": pr.number, "title": pr.title}
            else:
                self.log(f"Autonomous conflict resolution failed for PR #{pr.number}")

        # Fallback to comment
        return self.notify_conflicts(pr)

    def resolve_conflicts_autonomously(self, pr):
        """
        Attempt to resolve merge conflicts autonomously.
        """
        try:
            # Construct authenticated URL
            token = getattr(self.github_client, 'token', os.getenv("GITHUB_TOKEN"))

            # Use the configured AI client for conflict resolution
            conflict_client = self.ai_client

            repo_url = pr.base.repo.clone_url.replace("https://", f"https://x-access-token:{token}@")
            head_repo_url = pr.head.repo.clone_url.replace("https://", f"https://x-access-token:{token}@")

            with tempfile.TemporaryDirectory() as temp_dir:
                repo_dir = os.path.join(temp_dir, "repo")

                # Rule: Clone the PR's head repository (the fork)
                subprocess.run(["git", "clone", head_repo_url, repo_dir], check=True, capture_output=True)

                # Setup user
                subprocess.run(["git", "config", "user.email", "jules@google.com"], cwd=repo_dir, check=True)
                subprocess.run(["git", "config", "user.name", "Jules"], cwd=repo_dir, check=True)

                # Rule: Add the base repository as an 'upstream' remote
                # If it's the same repo, we can call it 'upstream' too or just use origin/upstream convention
                if pr.head.repo.id != pr.base.repo.id:
                    subprocess.run(["git", "remote", "add", "upstream", repo_url], cwd=repo_dir, check=True)
                    remote_base = "upstream"
                else:
                    # Same repo, upstream is origin
                    remote_base = "origin"

                # Checkout PR branch
                subprocess.run(["git", "checkout", pr.head.ref], cwd=repo_dir, check=True)

                # Rule: Merges the upstream base branch into the local branch
                target_branch = pr.base.ref
                subprocess.run(["git", "fetch", remote_base, target_branch], cwd=repo_dir, check=True)

                try:
                    subprocess.run(["git", "merge", f"{remote_base}/{target_branch}"], cwd=repo_dir, check=True, capture_output=True)
                    # If merge succeeds without conflict, push and return
                    subprocess.run(["git", "push"], cwd=repo_dir, check=True)
                    return True
                except subprocess.CalledProcessError:
                    self.log("Merge failed as expected, resolving conflicts...")

                # Get conflicted files
                status = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo_dir).decode("utf-8")
                conflicted_files = status.strip().split("\n")

                for file_path in conflicted_files:
                    if not file_path:
                        continue
                    full_path = os.path.join(repo_dir, file_path)

                    try:
                        with open(full_path) as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        self.log(f"Skipping binary file: {file_path}")
                        continue

                    # Extract conflict blocks and resolve
                    conflict_pattern = re.compile(r"(<<<<<<<.*?=======(?:.*?)>>>>>>>[^\n]*\n?)", re.DOTALL)

                    resolved_content = content
                    matches = conflict_pattern.findall(content)
                    if not matches:
                        self.log(f"No markers found in {file_path}")
                        continue

                    for match in matches:
                        resolved_block = conflict_client.resolve_conflict(content, match)
                        resolved_content = resolved_content.replace(match, resolved_block)

                    with open(full_path, "w") as f:
                        f.write(resolved_content)

                    subprocess.run(["git", "add", file_path], cwd=repo_dir, check=True)

                # Commit and push
                subprocess.run(["git", "commit", "-m", "fix: resolve merge conflicts autonomously"], cwd=repo_dir, check=True)

                # Push back to origin (which is the fork)
                subprocess.run(["git", "push", "origin", pr.head.ref], cwd=repo_dir, check=True)

                return True

        except Exception as e:
            self.log(f"Error resolving conflicts: {e}", "ERROR")
            return False

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
            self.log(f"Error checking existing comments for PR #{pr.number}: {e}", "ERROR")  # pragma: no cover

        comment_body = (
            "⚠️ **Conflitos de Merge Detectados**\n\n"
            "Olá @juninmd, existem conflitos que impedem o merge automático deste PR.\n"
            "Por favor, resolva os conflitos localmente ou via interface do GitHub para que eu possa processar o merge novamente."
        )

        try:
            pr.create_issue_comment(comment_body)
            self.log(f"Posted conflict notification on PR #{pr.number}")
        except Exception as e:
            self.log(f"Failed to post conflict notification for PR #{pr.number}: {e}", "ERROR")  # pragma: no cover

        return {"action": "conflicts_detected", "pr": pr.number, "title": pr.title}

    def handle_pipeline_failure(self, pr, failure_description):
        """Request corrections for pipeline failures."""
        try:
            comments = self.github_client.get_issue_comments(pr)
            for comment in reversed(list(comments)):
                if "Pipeline failed with status:" in comment.body or "❌ Pipeline Failure" in comment.body:
                    self.log(f"PR #{pr.number} already has a pipeline failure comment")
                    return
        except Exception as e:
            self.log(f"Error checking existing comments for PR #{pr.number}: {e}", "ERROR")  # pragma: no cover

        try:
            comment_body = self.ai_client.generate_pr_comment(failure_description)
        except Exception as e:
            self.log(f"AI Client failed to generate comment: {e}", "WARNING")
            comment_body = self._generate_pipeline_failure_comment(pr, failure_description)

        pr.create_issue_comment(comment_body)
        self.log(f"Posted pipeline failure comment on PR #{pr.number}")

    def _generate_pipeline_failure_comment(self, pr, failure_description: str) -> str:
        """Generate a pipeline failure comment using a template."""
        return (
            f"❌ **Pipeline Failure Detected**\n\n"
            f"Hi @juninmd, the CI/CD pipeline for this PR has failed.\n\n"
            f"**Failure Details:**\n"
            f"```\n{failure_description}\n```\n\n"
            f"Please review the errors above and push corrections to resolve these issues. "
            f"Once all checks pass, I'll be able to merge this PR automatically.\n\n"
            f"Thank you! 🙏"
        )
