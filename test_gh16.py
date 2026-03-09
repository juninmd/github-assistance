import os
import requests

token = os.environ.get('GITHUB_TOKEN', '')
headers = {'Authorization': f'token {token}'} if token else {}

queries = [
    'is:pr+is:open+repo:octokit/octokit.js+author:app/dependabot',
    'is:pr+is:open+repo:octokit/octokit.js+author:app/renovate',
]
results = []
for q in queries:
    r = requests.get(f'https://api.github.com/search/issues?q={q}', headers=headers)
    if r.status_code == 200:
        results.extend(r.json().get('items', []))
    else:
        print("error", r.json())

print("Total results:", len(results))
