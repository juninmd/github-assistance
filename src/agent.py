import re
import subprocess
import os
from src.github_client import GithubClient
from src.ai_client import AIClient

class Agent:
    def __init__(self, github_client: GithubClient, ai_client: AIClient, target_author: str = "google-labs-jules", target_owner: str = "juninmd"):
        self.github_client = github_client
        self.ai_client = ai_client
        self.target_author = target_author
        self.target_owner = target_owner

    def run(self):
        """
        Main entry point: Scans PRs and processes them.
        """
        # Search for PRs in repositories owned by target_owner, created by target_author
        query = f"is:pr state:open author:{self.target_author} user:{self.target_owner}"
        print(f"Scanning for PRs with query: {query}")

        issues = self.github_client.search_prs(query)

        for issue in issues:
            print(f"Processing PR #{issue.number} in {issue.repository.full_name}: {issue.title}")
            try:
                # Convert to PullRequest object to access full API
                pr = self.github_client.get_pr_from_issue(issue)
                self.process_pr(pr)
            except Exception as e:
                print(f"Error processing PR #{issue.number}: {e}")

    def process_pr(self, pr):
        # 1. Check for Conflicts
        if pr.mergeable is False:
            print(f"PR #{pr.number} has conflicts.")
            self.handle_conflicts(pr)
            return

        # 2. Check Pipeline Status
        # Check commits for status
        try:
            commits = pr.get_commits()
            if commits.totalCount > 0:
                last_commit = commits.reversed[0]
                statuses = last_commit.get_statuses()
                # If any failure/error status exists
                failed_status = next((s for s in statuses if s.state in ['failure', 'error']), None)

                if failed_status:
                    print(f"PR #{pr.number} has pipeline failures.")
                    self.handle_pipeline_failure(pr, failed_status)
                    return
        except Exception as e:
            print(f"Error checking status for PR #{pr.number}: {e}")
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
            # Insert token for auth
            clone_url = pr.base.repo.clone_url.replace("https://", f"https://x-access-token:{self.github_client.token}@")

            # Setup local workspace
            work_dir = f"/tmp/pr_{repo_name.replace('/', '_')}_{pr.number}"
            if os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

            # Clone and setup
            print(f"Cloning {repo_name} to {work_dir}...")
            subprocess.run(["git", "clone", clone_url, work_dir], check=True, capture_output=True)
            subprocess.run(["git", "checkout", pr_branch], cwd=work_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "agent@juninmd.com"], cwd=work_dir, check=True)
            subprocess.run(["git", "config", "user.name", "PR Agent"], cwd=work_dir, check=True)

            # Attempt merge to generate conflict markers
            try:
                subprocess.run(["git", "merge", f"origin/{base_branch}"], cwd=work_dir, check=True, capture_output=True)
                # If merge succeeds without conflict, push it? No, pr.mergeable was False.
                subprocess.run(["git", "push"], cwd=work_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # Merge failed, so there are conflicts.
                # Identify conflicting files
                status_output = subprocess.check_output(["git", "status", "--porcelain"], cwd=work_dir).decode("utf-8")
                conflicted_files = []
                for line in status_output.splitlines():
                    if line.startswith("UU"): # Both modified
                        conflicted_files.append(line[3:])

                if not conflicted_files:
                    print("No conflicting files found despite merge failure.")
                    return

                print(f"Resolving conflicts in: {conflicted_files}")

                for file_path in conflicted_files:
                    full_path = os.path.join(work_dir, file_path)
                    with open(full_path, "r") as f:
                        content = f.read()

                    # Resolve conflicts loop
                    while "<<<<<<<" in content:
                        start = content.find("<<<<<<<")
                        end = content.find(">>>>>>>")
                        if end == -1: break
                        end_of_line = content.find("\n", end)

                        block = content[start:end_of_line+1]

                        # Call AI
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
        finally:
            if os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

    def handle_pipeline_failure(self, pr, status):
        comment = self.ai_client.generate_pr_comment(
            f"Pipeline failed with status: {status.description}. context: {status.context}"
        )
        self.github_client.comment_on_pr(pr, comment)
