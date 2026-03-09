import os
import requests
import json

token = os.environ.get('GITHUB_TOKEN', '')
headers = {'Authorization': f'token {token}'} if token else {}

r = requests.get('https://api.github.com/search/issues?q=is:pr+is:open+repo:octokit/octokit.js+author:app/renovate', headers=headers)
print("app/renovate")
for item in r.json().get('items', []):
    print(item['number'])

r = requests.get('https://api.github.com/search/issues?q=is:pr+is:open+repo:octokit/octokit.js+author:app/dependabot+author:app/renovate', headers=headers)
print("both")
for item in r.json().get('items', []):
    print(item['number'])
