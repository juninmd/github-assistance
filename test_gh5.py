import os
from github import Github

token = os.environ.get('GITHUB_TOKEN', '')
g = Github(auth=__import__('github').Auth.Token(token)) if token else Github()

# Now testing combinations without parens
queries = [
    'is:pr is:open repo:octokit/octokit.js author:app/dependabot OR author:app/renovate',
    'is:pr is:open repo:octokit/octokit.js author:dependabot[bot] OR author:renovate[bot]',
    'is:pr is:open repo:octokit/octokit.js author:app/dependabot author:app/renovate'
]

for q in queries:
    try:
        res = g.search_issues(q)
        print(f"Query: {q}")
        print(f"Count: {res.totalCount}")
    except Exception as e:
        print(f"Query: {q}")
        print(f"Error: {e}")
