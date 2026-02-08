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
            "merged": [],
            "conflicts_resolved": [],
            "pipeline_failures": [],
            "skipped": [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            issues = self.github_client.search_prs(query)

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

        return results

    def process_pr(self, pr) -> Dict[str, Any]:
        """
        Process a single PR according to the rules.

        Args:
            pr: GitHub PR object

        Returns:
            Processing result
        """
        # Safety Check: Verify Author
        if pr.user.login not in self.allowed_authors:
            self.log(f"Skipping PR #{pr.number} from author {pr.user.login}")
            return {
                "action": "skipped",
                "pr": pr.number,
                "reason": "untrusted_author",
                "author": pr.user.login
            }

        # Check for Conflicts
        if pr.mergeable is None:
            self.log(f"PR #{pr.number} mergeability unknown")
            return {"action": "skipped", "pr": pr.number, "reason": "mergeability_unknown"}

        if pr.mergeable is False:
            self.log(f"PR #{pr.number} has conflicts")
            self.handle_conflicts(pr)
            return {"action": "conflicts_resolved", "pr": pr.number}

        # Check Pipeline Status
        pipeline_success = False
        try:
            commits = pr.get_commits()
            if commits.totalCount > 0:
                last_commit = commits.reversed[0]
                combined_status = last_commit.get_combined_status()
                state = combined_status.state

                if state in ['failure', 'error']:
                    self.log(f"PR #{pr.number} has pipeline failures")
                    self.handle_pipeline_failure(pr, combined_status)
                    return {"action": "pipeline_failure", "pr": pr.number, "state": state}
                elif state == 'success':
                    pipeline_success = True
                else:
                    self.log(f"PR #{pr.number} pipeline is '{state}'")
                    return {"action": "skipped", "pr": pr.number, "reason": f"pipeline_{state}"}
        except Exception as e:
            self.log(f"Error checking status for PR #{pr.number}: {e}", "ERROR")
            return {"action": "error", "pr": pr.number, "error": str(e)}

        # Auto-Merge
        if pr.mergeable is True and pipeline_success:
            self.log(f"PR #{pr.number} is ready to merge")
            success, msg = self.github_client.merge_pr(pr)
            if not success:
                self.log(f"Failed to merge PR #{pr.number}: {msg}", "ERROR")
                return {"action": "merge_failed", "pr": pr.number, "error": msg}
            else:
                self.github_client.send_telegram_notification(pr)
                return {"action": "merged", "pr": pr.number, "title": pr.title}

        return {"action": "skipped", "pr": pr.number, "reason": "unknown"}

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
                subprocess.run(["git", "push"], cwd=work_dir, check=True, capture_output=True)
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
                    with open(full_path, "r") as f:
                        content = f.read()

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

    def handle_pipeline_failure(self, pr, status):
        """Request corrections for pipeline failures."""
        try:
            comments = self.github_client.get_issue_comments(pr)
            for comment in reversed(list(comments)):
                if "Pipeline failed with status:" in comment.body:
                    self.log(f"PR #{pr.number} already has a pipeline failure comment")
                    return
        except Exception as e:
            self.log(f"Error checking existing comments for PR #{pr.number}: {e}", "ERROR")

        failed_statuses = [s for s in status.statuses if s.state in ['failure', 'error']]
        if not failed_statuses:
            issue_description = f"Pipeline state is {status.state}"
        else:
            details = [f"- {s.context}: {s.description}" for s in failed_statuses]
            issue_description = "Pipeline failed with status:\n" + "\n".join(details)

        comment = self.ai_client.generate_pr_comment(issue_description)
        pr.create_issue_comment(comment)
        self.log(f"Posted pipeline failure comment on PR #{pr.number}")
