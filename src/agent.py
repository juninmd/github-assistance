import re
import subprocess
import os
from src.github_client import GithubClient
from src.ai_client import AIClient

class Agent:
    def __init__(self, github_client: GithubClient, ai_client: AIClient, target_author: str = "google-labs-jules"):
        self.github_client = github_client
        self.ai_client = ai_client
        self.target_author = target_author

    def run(self):
        """
        Main entry point: Scans PRs and processes them.
        """
        print(f"Scanning for PRs from {self.target_author}...")
        issues = self.github_client.get_pull_requests(author=self.target_author)

        for issue in issues:
            print(f"Processing PR #{issue.number}: {issue.title}")
            pr = self.github_client.get_pr_details(issue.number)
            self.process_pr(pr)

    def process_pr(self, pr):
        # 1. Check for Conflicts
        # We check 'mergeable' state. If False, we try to resolve.
        if pr.mergeable is False:
            print(f"PR #{pr.number} has conflicts.")
            self.handle_conflicts(pr)
            return

        # 2. Check Pipeline Status
        # Check commits for status
        last_commit = pr.get_commits().reversed[0]
        statuses = last_commit.get_statuses()
        # If any failure/error status exists
        failed_status = next((s for s in statuses if s.state in ['failure', 'error']), None)

        if failed_status:
            print(f"PR #{pr.number} has pipeline failures.")
            self.handle_pipeline_failure(pr, failed_status)
            return

        # 3. Auto-Merge
        if pr.mergeable is True:
             print(f"PR #{pr.number} is clean. Merging...")
             self.github_client.merge_pr(pr)

    def handle_conflicts(self, pr):
        """
        Resolves conflicts by running git commands locally.
        """
        try:
            repo_name = pr.base.repo.full_name
            pr_branch = pr.head.ref
            base_branch = pr.base.ref
            clone_url = pr.base.repo.clone_url.replace("https://", f"https://x-access-token:{self.github_client.token}@")

            # Setup local workspace
            work_dir = f"/tmp/pr_{pr.number}"
            if os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

            # Clone and setup
            subprocess.run(["git", "clone", clone_url, work_dir], check=True)
            subprocess.run(["git", "checkout", pr_branch], cwd=work_dir, check=True)
            subprocess.run(["git", "config", "user.email", "agent@juninmd.com"], cwd=work_dir, check=True)
            subprocess.run(["git", "config", "user.name", "PR Agent"], cwd=work_dir, check=True)

            # Attempt merge to generate conflict markers
            try:
                subprocess.run(["git", "merge", f"origin/{base_branch}"], cwd=work_dir, check=True)
                # If merge succeeds without conflict, push it? No, pr.mergeable was False.
                # It might have been a false positive or just needs update.
                subprocess.run(["git", "push"], cwd=work_dir, check=True)
            except subprocess.CalledProcessError:
                # Merge failed, so there are conflicts.
                # Identify conflicting files
                status_output = subprocess.check_output(["git", "status", "--porcelain"], cwd=work_dir).decode("utf-8")
                conflicted_files = []
                for line in status_output.splitlines():
                    if line.startswith("UU"): # Both modified
                        conflicted_files.append(line[3:])

                for file_path in conflicted_files:
                    full_path = os.path.join(work_dir, file_path)
                    with open(full_path, "r") as f:
                        content = f.read()

                    # Find blocks
                    # Simplified regex for <<<<<<< HEAD ... ======= ... >>>>>>> branch
                    # Note: We need to handle multiple conflicts in one file
                    # We will loop until all are resolved

                    while "<<<<<<<" in content:
                        # Extract the first conflict block
                        # This is a naive extraction.
                        start = content.find("<<<<<<<")
                        end = content.find(">>>>>>>")
                        if end == -1: break # Should not happen if markers are correct
                        end_of_line = content.find("\n", end)

                        block = content[start:end_of_line+1]

                        resolved_block = self.ai_client.resolve_conflict(content, block)
                        content = content.replace(block, resolved_block)

                    with open(full_path, "w") as f:
                        f.write(content)

                    subprocess.run(["git", "add", file_path], cwd=work_dir, check=True)

                # Commit and push
                subprocess.run(["git", "commit", "-m", "fix: resolve merge conflicts via AI Agent"], cwd=work_dir, check=True)
                subprocess.run(["git", "push"], cwd=work_dir, check=True)
                print(f"Conflicts resolved and pushed for PR #{pr.number}")

        except Exception as e:
            print(f"Failed to resolve conflicts for PR #{pr.number}: {e}")

    def handle_pipeline_failure(self, pr, status):
        comment = self.ai_client.generate_pr_comment(
            f"Pipeline failed with status: {status.description}. context: {status.context}"
        )
        self.github_client.comment_on_pr(pr, comment)
