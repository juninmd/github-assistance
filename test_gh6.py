import os
import requests

token = os.environ.get('GITHUB_TOKEN', '')
headers = {'Authorization': f'token {token}'} if token else {}

queries = [
    'is:pr+is:open+repo:octokit/octokit.js+author:app/dependabot+author:app/renovate',
]

for q in queries:
    r = requests.get(f'https://api.github.com/search/issues?q={q}', headers=headers)
    print(f"Query: {q} => Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.json()}")
    else:
        print(f"Count: {r.json().get('total_count')}")
