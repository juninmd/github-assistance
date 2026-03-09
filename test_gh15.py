import os
from github import Github

token = os.environ.get('GITHUB_TOKEN', '')
g = Github(auth=__import__('github').Auth.Token(token)) if token else Github()

q = 'is:pr is:open archived:false user:juninmd author:app/dependabot author:app/renovate'
try:
    res = g.search_issues(q)
    print(f"Count: {res.totalCount}")
except Exception as e:
    print(f"Error: {e}")
