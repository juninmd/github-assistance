import os
from github import Github

token = os.environ.get('GITHUB_TOKEN', '')
g = Github(auth=__import__('github').Auth.Token(token)) if token else Github()

q = 'is:pr is:open repo:octokit/octokit.js author:app/dependabot author:app/renovate'
try:
    res = list(g.search_issues(q))
    print(f"Count: {len(res)}")
    for item in res:
        print(item.number)
except Exception as e:
    print(f"Error: {e}")
