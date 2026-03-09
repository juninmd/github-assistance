import os
import requests

token = os.environ.get('GITHUB_TOKEN', '')
headers = {'Authorization': f'token {token}'} if token else {}

# Appending parameters one by one to see which combinations work
queries = [
    'is:pr is:open archived:false user:juninmd',
    'is:pr is:open archived:false user:juninmd author:app/dependabot',
    'is:pr is:open archived:false user:juninmd author:app/renovate',
    'is:pr is:open archived:false user:juninmd author:dependabot[bot]',
    'is:pr is:open archived:false user:juninmd author:renovate[bot]',
    'is:pr is:open archived:false user:juninmd author:app/dependabot author:app/renovate',
    'is:pr is:open archived:false user:juninmd author:dependabot[bot] author:renovate[bot]'
]

for q in queries:
    r = requests.get(f'https://api.github.com/search/issues?q={q}', headers=headers)
    print(f"Query: {q} => Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.json()}")
    else:
        print(f"Count: {r.json().get('total_count')}")
