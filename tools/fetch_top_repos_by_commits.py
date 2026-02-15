#!/usr/bin/env python3
"""
Fetch top N repositories by total commit count for a GitHub user and update
config/repositories.json.

Usage:
  python tools/fetch_top_repos_by_commits.py --user USERNAME --top 30 --out config/repositories.json --replace

Notes:
- Uses GITHUB_TOKEN env var if available to increase rate limits.
- Commit count is approximated by summing the `contributions` field from the
  Contributors API for each repo (includes anonymous contributors).
"""
import argparse
import json
import os
import sys
import time
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen


def request_json(url, token=None):
    req = Request(url, headers={"User-Agent": "github-assistant-script"})
    if token:
        req.add_header("Authorization", f"token {token}")
    with urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        headers = dict(resp.getheaders())
    return json.loads(body), headers


def get_all_contributors_contributions(contribs_url, token=None):
    # contributors_url usually ends with /contributors; use per_page=100 and follow pagination
    url = contribs_url + "?per_page=100&anon=1"
    total = 0
    while url:
        arr, headers = request_json(url, token)
        if not isinstance(arr, list):
            break
        for c in arr:
            total += c.get("contributions", 0)
        link = headers.get("Link")
        next_url = None
        if link:
            # parse Link header to find rel="next"
            parts = [p.strip() for p in link.split(",")]
            for p in parts:
                if 'rel="next"' in p:
                    # format: <https://...>; rel="next"
                    start = p.find("<") + 1
                    end = p.find(">", start)
                    next_url = p[start:end]
                    break
        url = next_url
        if url:
            time.sleep(0.1)
    return total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", "-u", required=True)
    p.add_argument("--top", "-n", type=int, default=30)
    p.add_argument("--out", default="config/repositories.json")
    p.add_argument("--replace", action="store_true", help="Replace repositories array")
    args = p.parse_args()

    token = os.environ.get("GITHUB_TOKEN")

    repos_url = f"https://api.github.com/users/{args.user}/repos?per_page=100"
    print(f"Fetching repos list for {args.user}...")
    repos, _ = request_json(repos_url, token)
    if not isinstance(repos, list):
        print("Unexpected response for repo list", file=sys.stderr)
        sys.exit(1)

    results = []
    total_repos = len(repos)
    for i, r in enumerate(repos, start=1):
        name = r.get("name")
        full_name = r.get("full_name")
        contribs_url = r.get("contributors_url")
        print(f"[{i}/{total_repos}] {full_name}: fetching contributors...")
        try:
            commits = get_all_contributors_contributions(contribs_url, token)
        except Exception as e:
            print(f"  failed to fetch contributors for {full_name}: {e}")
            commits = 0
        results.append({"full_name": full_name, "commits": commits})
        # be gentle with rate limits
        time.sleep(0.12)

    # sort and pick top N
    results.sort(key=lambda x: x["commits"], reverse=True)
    top = results[: args.top]

    print("\nTop repositories by estimated commits:")
    for idx, r in enumerate(top, start=1):
        print(f"{idx:2d}. {r['full_name']} — {r['commits']} commits")

    # read output JSON and update
    out_path = args.out
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {}

    new_repos = [r["full_name"] for r in top]

    if args.replace or "repositories" not in cfg:
        cfg["repositories"] = new_repos
    else:
        # append unique ones preserving existing order first
        existing = cfg.get("repositories", [])
        merged = existing[:]
        for r in new_repos:
            if r not in merged:
                merged.append(r)
        cfg["repositories"] = merged

    # ensure description remains if present
    if "description" not in cfg:
        cfg["description"] = "List of repositories that agents are allowed to work on. Add repositories in 'owner/repo' format."

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    print(f"\nUpdated {out_path} with top {len(new_repos)} repositories.")


if __name__ == "__main__":
    main()
