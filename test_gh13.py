import os
import requests

token = os.environ.get('GITHUB_TOKEN', '')
headers = {'Authorization': f'token {token}'} if token else {}

r = requests.get('https://api.github.com/search/issues?q=is:pr+is:open+repo:fastapi/fastapi+author:app/dependabot', headers=headers)
print("app/dependabot")
if r.status_code == 200:
    for item in r.json().get('items', [])[:2]:
        print(item['number'])

r = requests.get('https://api.github.com/search/issues?q=is:pr+is:open+repo:fastapi/fastapi+author:app/renovate', headers=headers)
print("app/renovate")
if r.status_code == 200:
    for item in r.json().get('items', [])[:2]:
        print(item['number'])

r = requests.get('https://api.github.com/search/issues?q=is:pr+is:open+repo:fastapi/fastapi+author:app/dependabot+author:app/renovate', headers=headers)
print("both")
if r.status_code == 200:
    for item in r.json().get('items', [])[:2]:
        print(item['number'])
