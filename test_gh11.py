import os
from github import Github

token = os.environ.get('GITHUB_TOKEN', '')
g = Github(auth=__import__('github').Auth.Token(token)) if token else Github()

q = 'is:pr is:open repo:octokit/octokit.js author:app/dependabot OR author:app/renovate'
try:
    res = g.search_issues(q)
    print(f"Count: {res.totalCount}")
    for item in res:
        print(item.number)
except Exception as e:
    print(f"Error: {e}")
