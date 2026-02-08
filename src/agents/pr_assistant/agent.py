"""
PR Assistant Agent - Handles automated PR verification and merging.
This is a refactored version of the original Agent class.
"""
import re
import subprocess
import os
from typing import Dict, Any
from datetime import datetime
from src.agents.base_agent import BaseAgent
from src.ai_client import AIClient


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
        ai_client: AIClient,
        target_owner: str = "juninmd",
        allowed_authors: list = None,
        **kwargs
    ):
        """
        Initialize PR Assistant Agent.

        Args:
            ai_client: AI client for conflict resolution
            target_owner: GitHub username to monitor
            allowed_authors: List of trusted PR authors
        """
        super().__init__(*args, name="PRAssistant", **kwargs)
        self.ai_client = ai_client
        self.target_owner = target_owner
        self.allowed_authors = allowed_authors or [
            "juninmd",
            "Copilot",
            "imgbot[bot]",
            "renovate[bot]",
            "dependabot[bot]",
            "Jules da Google"
        ]

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
                    pr_result = self.process_pr(pr)

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
                        "error": str(e)
                    })

        except Exception as e:
            self.log(f"Error scanning PRs: {e}", "ERROR")
            return {"status": "error", "error": str(e)}

        self.log(f"Completed: {len(results['merged'])} merged, "
                f"{len(results['conflicts_resolved'])} conflicts resolved, "
                f"{len(results['pipeline_failures'])} pipeline issues")

        # Send Telegram Summary
        summary_text = (
            "📊 *PR Assistant Summary*\n\n"
            f"🔍 *PRs Analisados:* {results['total_found']}\n"
            f"✅ *Mergeados:* {len(results['merged'])}\n"
            f"🛠️ *Conflitos Resolvidos:* {len(results['conflicts_resolved'])}\n"
            f"❌ *Falhas de Pipeline:* {len(results['pipeline_failures'])}\n"
            f"⏩ *Pulados/Pendentes:* {len(results['skipped'])}\n\n"
            f"Dono: `{self.target_owner}`"
        )
        self.github_client.send_telegram_msg(summary_text)

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
            self.handle_conflicts(pr)
            return {"action": "conflicts_resolved", "pr": pr.number}
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
        """Resolve conflicts by running git commands locally."""
        work_dir = None
        try:
            repo_name = pr.base.repo.full_name
            pr_branch = pr.head.ref
            base_branch = pr.base.ref

            if pr.head.repo is None:
                self.log(f"PR #{pr.number} head repository is missing", "WARNING")
                return

            head_clone_url = pr.head.repo.clone_url.replace(
                "https://", f"https://x-access-token:{self.github_client.token}@"
            )
            base_clone_url = pr.base.repo.clone_url.replace(
                "https://", f"https://x-access-token:{self.github_client.token}@"
            )

            work_dir = f"/tmp/pr_{repo_name.replace('/', '_')}_{pr.number}"
            if os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

            self.log(f"Cloning {pr.head.repo.full_name} to {work_dir}...")
            subprocess.run(["git", "clone", head_clone_url, work_dir], check=True, capture_output=True)
            subprocess.run(["git", "checkout", pr_branch], cwd=work_dir, check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "upstream", base_clone_url], cwd=work_dir, check=True)
            subprocess.run(["git", "fetch", "upstream"], cwd=work_dir, check=True)
            subprocess.run(["git", "config", "user.email", "agent@juninmd.com"], cwd=work_dir, check=True)
            subprocess.run(["git", "config", "user.name", "PR Agent"], cwd=work_dir, check=True)

            try:
                subprocess.run(["git", "merge", f"upstream/{base_branch}"], cwd=work_dir, check=True, capture_output=True)
                try:
                   subprocess.run(["git", "push"], cwd=work_dir, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                   self.log(f"Merge succeeded locally but failed to push PR #{pr.number}: {e}", "ERROR")
                   return
            except subprocess.CalledProcessError:
                diff_output = subprocess.check_output(
                    ["git", "diff", "--name-only", "--diff-filter=U"],
                    cwd=work_dir
                ).decode("utf-8")

                conflicted_files = [line.strip() for line in diff_output.splitlines() if line.strip()]

                if not conflicted_files:
                    self.log("No conflicting files found despite merge failure")
                    return

                self.log(f"Resolving conflicts in: {conflicted_files}")

                for file_path in conflicted_files:
                    full_path = os.path.join(work_dir, file_path)
                    
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except UnicodeDecodeError:
                        self.log(f"Skipping AI conflict resolution for binary file: {file_path}", "INFO")
                        continue

                    while True:
                        start = content.find("<<<<<<<")
                        if start == -1:
                            break
                        end = content.find(">>>>>>>", start)
                        if end == -1:
                            break
                        end_of_line = content.find("\n", end)
                        if end_of_line == -1:
                            end_of_line = len(content)

                        block = content[start:end_of_line+1]
                        resolved_block = self.ai_client.resolve_conflict(content, block)

                        if "<<<<<<<" in resolved_block or ">>>>>>>" in resolved_block:
                            raise ValueError("AI returned conflict markers in resolved block")

                        content = content[:start] + resolved_block + content[end_of_line+1:]

                    with open(full_path, "w") as f:
                        f.write(content)

                    subprocess.run(["git", "add", file_path], cwd=work_dir, check=True)

                subprocess.run(["git", "commit", "-m", "fix: resolve merge conflicts via AI Agent"], cwd=work_dir, check=True)
                subprocess.run(["git", "push"], cwd=work_dir, check=True)
                self.log(f"Conflicts resolved and pushed for PR #{pr.number}")

        except Exception as e:
            self.log(f"Failed to resolve conflicts for PR #{pr.number}: {e}", "ERROR")
        finally:
            if work_dir and os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

    def handle_pipeline_failure(self, pr, failure_description):
        """Request corrections for pipeline failures."""
        try:
            comments = self.github_client.get_issue_comments(pr)
            for comment in reversed(list(comments)):
                if "Pipeline failed with status:" in comment.body:
                    self.log(f"PR #{pr.number} already has a pipeline failure comment")
                    return
        except Exception as e:
            self.log(f"Error checking existing comments for PR #{pr.number}: {e}", "ERROR")

        comment = self.ai_client.generate_pr_comment(failure_description)
        pr.create_issue_comment(comment)
        self.log(f"Posted pipeline failure comment on PR #{pr.number}")
