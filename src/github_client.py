import os
from github import Github, GithubException

class GithubClient:
    def __init__(self, token=None, repo_name=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required")
        self.g = Github(self.token)
        self.repo_name = repo_name

    def get_repo(self):
        return self.g.get_repo(self.repo_name)

    def get_pull_requests(self, state='open', author=None):
        """
        Fetches PRs. If author is provided, filters by author.
        Note: PyGithub's get_pulls doesn't filter by author directly in the API call for all endpoints,
        so we might need to filter client-side or use search.
        """
        repo = self.get_repo()
        # Using search is often better for filtering by author
        if author:
            query = f"repo:{self.repo_name} is:pr is:{state} author:{author}"
            return self.g.search_issues(query)
        else:
            return repo.get_pulls(state=state)

    def get_pr_details(self, pr_number):
        repo = self.get_repo()
        return repo.get_pull(pr_number)

    def get_file_content(self, pr, file_path):
        """
        Gets the content of a file from the PR's head branch.
        """
        try:
            repo = self.get_repo()
            # Get contents from the specific ref (branch) of the PR
            contents = repo.get_contents(file_path, ref=pr.head.sha)
            return contents.decoded_content.decode('utf-8')
        except GithubException:
            return None

    def merge_pr(self, pr):
        try:
            pr.merge()
            return True, "Merged successfully"
        except GithubException as e:
            return False, str(e)

    def comment_on_pr(self, pr, body):
        pr.create_issue_comment(body)

    def commit_file(self, pr, file_path, content, message):
        """
        Updates a file in the PR branch.
        """
        repo = self.get_repo()
        try:
            contents = repo.get_contents(file_path, ref=pr.head.sha)
            repo.update_file(contents.path, message, content, contents.sha, branch=pr.head.ref)
            return True
        except GithubException as e:
            print(f"Error committing file: {e}")
            return False
