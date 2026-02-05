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
        """
        Processes a single PR according to the rules:
        1. Resolve conflicts autonomously if opened by Jules da Google.
        2. Request pipeline corrections.
        3. Auto-merge if clean and successful.
        """
        # 0. Safety Check: Verify Author
        if pr.user.login != self.target_author:
            print(f"Skipping PR #{pr.number} from author {pr.user.login} (expected {self.target_author})")
            return

        # 1. Check for Conflicts
        if pr.mergeable is None:
            print(f"PR #{pr.number} mergeability is unknown (GitHub is computing). Skipping.")
            return

        if pr.mergeable is False:
            print(f"PR #{pr.number} has conflicts.")
            self.handle_conflicts(pr)
            return

        # 2. Check Pipeline Status
        pipeline_success = False
        try:
            commits = pr.get_commits()
            if commits.totalCount > 0:
                last_commit = commits.reversed[0]
                combined_status = last_commit.get_combined_status()
                state = combined_status.state

                if state in ['failure', 'error']:
                    print(f"PR #{pr.number} has pipeline failures.")
                    self.handle_pipeline_failure(pr, combined_status)
                    return
                elif state == 'success':
                    pipeline_success = True
                else:
                    print(f"PR #{pr.number} pipeline is '{state}'. Skipping.")
                    return
        except Exception as e:
            print(f"Error checking status for PR #{pr.number}: {e}")
            return

        # 3. Auto-Merge
        if pr.mergeable is True and pipeline_success:
             print(f"PR #{pr.number} is clean and pipeline passed. Merging...")
             self.github_client.merge_pr(pr)

    def handle_conflicts(self, pr):
        """
        Resolves conflicts by running git commands locally.
        """
        work_dir = None
        try:
            repo_name = pr.base.repo.full_name
            pr_branch = pr.head.ref
            base_branch = pr.base.ref

            if pr.head.repo is None:
                print(f"PR #{pr.number} head repository is missing (deleted fork?). Skipping conflict resolution.")
                return

            # Insert token for auth - Use HEAD repo for the source (where to push to)
            head_clone_url = pr.head.repo.clone_url.replace("https://", f"https://x-access-token:{self.github_client.token}@")
            base_clone_url = pr.base.repo.clone_url.replace("https://", f"https://x-access-token:{self.github_client.token}@")

            # Setup local workspace
            work_dir = f"/tmp/pr_{repo_name.replace('/', '_')}_{pr.number}"
            if os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

            # Clone and setup
            print(f"Cloning {pr.head.repo.full_name} to {work_dir}...")
            subprocess.run(["git", "clone", head_clone_url, work_dir], check=True, capture_output=True)
            subprocess.run(["git", "checkout", pr_branch], cwd=work_dir, check=True, capture_output=True)

            # Add base repo as upstream to fetch the target branch
            subprocess.run(["git", "remote", "add", "upstream", base_clone_url], cwd=work_dir, check=True)
            subprocess.run(["git", "fetch", "upstream"], cwd=work_dir, check=True)

            subprocess.run(["git", "config", "user.email", "agent@juninmd.com"], cwd=work_dir, check=True)
            subprocess.run(["git", "config", "user.name", "PR Agent"], cwd=work_dir, check=True)

            # Attempt merge to generate conflict markers
            try:
                subprocess.run(["git", "merge", f"upstream/{base_branch}"], cwd=work_dir, check=True, capture_output=True)
                # If merge succeeds without conflict, push it? No, pr.mergeable was False.
                subprocess.run(["git", "push"], cwd=work_dir, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                # Merge failed, so there are conflicts.
                # Identify conflicting files
                # Use --diff-filter=U to find all unmerged files (UU, AA, DU, etc.)
                diff_output = subprocess.check_output(
                    ["git", "diff", "--name-only", "--diff-filter=U"],
                    cwd=work_dir
                ).decode("utf-8")

                conflicted_files = [line.strip() for line in diff_output.splitlines() if line.strip()]

                if not conflicted_files:
                    print("No conflicting files found despite merge failure.")
                    return

                print(f"Resolving conflicts in: {conflicted_files}")

                for file_path in conflicted_files:
                    full_path = os.path.join(work_dir, file_path)
                    with open(full_path, "r") as f:
                        content = f.read()

                    # Resolve conflicts loop
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

                        # Call AI
                        resolved_block = self.ai_client.resolve_conflict(content, block)

                        if "<<<<<<<" in resolved_block or ">>>>>>>" in resolved_block:
                            raise ValueError("AI returned conflict markers in resolved block")

                        # Replace only this occurrence by slicing
                        content = content[:start] + resolved_block + content[end_of_line+1:]

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
            if work_dir and os.path.exists(work_dir):
                subprocess.run(["rm", "-rf", work_dir])

    def handle_pipeline_failure(self, pr, status):
        # Check existing comments to avoid duplicates
        try:
            comments = self.github_client.get_issue_comments(pr)
            # Iterate backwards to find recent comments
            for comment in reversed(list(comments)):
                # We can't easily check author without knowing our own ID, but we can check the body content.
                if "Pipeline failed with status:" in comment.body:
                    print(f"PR #{pr.number} already has a pipeline failure comment. Skipping.")
                    return
        except Exception as e:
            print(f"Error checking existing comments for PR #{pr.number}: {e}")

        comment = self.ai_client.generate_pr_comment(
            f"Pipeline failed with status: {status.description}. context: {status.context}"
        )
        self.github_client.comment_on_pr(pr, comment)
