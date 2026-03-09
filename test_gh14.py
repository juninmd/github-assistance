import os
import requests
import time

token = os.environ.get('GITHUB_TOKEN', '')
headers = {'Authorization': f'token {token}'} if token else {}

def query(q):
    r = requests.get(f'https://api.github.com/search/issues?q={q}', headers=headers)
    print(q)
    if r.status_code == 200:
        data = r.json()
        print("count:", data.get('total_count'))
    else:
        print("error:", r.json())
    time.sleep(2)

query('is:pr+is:open+repo:tiangolo/fastapi+author:app/dependabot')
query('is:pr+is:open+repo:tiangolo/fastapi+author:app/renovate')
query('is:pr+is:open+repo:tiangolo/fastapi+author:app/dependabot+author:app/renovate')
