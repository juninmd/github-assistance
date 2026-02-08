# Troubleshooting Guide

## Common Issues and Solutions

### ❌ Error: 403 "Resource not accessible by integration" when merging PRs

**Error Message**:
```
[ERROR] Failed to merge PR #16: Resource not accessible by integration: 403
{"message": "Resource not accessible by integration", "documentation_url": "https://docs.github.com/rest/pulls/pulls#merge-a-pull-request", "status": "403"}
```

**Cause**:
The default `GITHUB_TOKEN` provided by GitHub Actions has **limited permissions** and cannot perform certain operations like merging PRs when workflows are triggered by:
- `schedule` (cron jobs)
- `workflow_dispatch` (manual triggers)

**Solution**:
Use a **Personal Access Token (PAT)** instead of the default `GITHUB_TOKEN`.

**Steps to Fix**:

1. **Create a Personal Access Token** (Fine-grained recommended):

   **Option A: Fine-grained Token (⭐ RECOMMENDED - More Secure)**:
   - Go to [GitHub Settings → Developer settings → Fine-grained tokens](https://github.com/settings/tokens?type=beta)
   - Click **Generate new token**
   - Token name: `PR Assistant Token`
   - Expiration: 90 days
   - Resource owner: Your account (juninmd)
   - Repository access: **All repositories** (or select specific repos)
   - Permissions → Repository permissions:
     - ✅ **Contents**: Read and write
     - ✅ **Pull requests**: Read and write
     - ✅ **Issues**: Read and write
     - ✅ **Workflows**: Read and write (optional)
   - Click **Generate token**
   - **Copy the token immediately!**

   **Option B: Classic Token**:
   - Go to [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
   - Click **Generate new token (classic)**
   - Name: `PR Assistant Token`
   - Expiration: 90 days
   - Select scopes:
     - ✅ `repo` (Full control of private repositories)
     - ✅ `workflow` (Update GitHub Action workflows)
   - Click **Generate token**
   - **Copy the token immediately!**

2. **Add token as a GitHub Secret**:
   - Go to your repository
   - Settings → Secrets and variables → Actions
   - Click **New repository secret**
   - Name: `GH_PAT`
   - Value: Paste your token
   - Click **Add secret**

3. **Workflows are already configured** to use `GH_PAT`:
   ```yaml
   env:
     GITHUB_TOKEN: ${{ secrets.GH_PAT || secrets.GITHUB_TOKEN }}
   ```
   This uses `GH_PAT` if available, otherwise falls back to `GITHUB_TOKEN`.

4. **Verify the setup**:
   - Go to Actions tab
   - Run **PR Assistant** workflow manually
   - Check if PRs can be merged successfully

**Why this happens**:
- `GITHUB_TOKEN`: Auto-generated, limited permissions, cannot merge PRs in scheduled workflows
- `GH_PAT`: User-generated, full permissions, can merge PRs

**Documentation**: [GitHub Actions Permissions](https://docs.github.com/en/actions/security-guides/automatic-token-authentication#permissions-for-the-github_token)

---

### ❌ TypeError: non-default argument follows default argument

**Error Message**:
```
TypeError: non-default argument 'jules_api_key' follows default argument
```

**Cause**:
Incorrect order of fields in a Python `@dataclass`. Fields without default values must come before fields with default values.

**Solution**:
Already fixed in `src/config/settings.py`. Fields are now properly ordered:
```python
@dataclass
class Settings:
    # Required fields (no defaults) - FIRST
    github_token: str
    jules_api_key: str

    # Optional fields (with defaults) - SECOND
    github_owner: str = "juninmd"
    ...
```

---

### ❌ No repositories in allowlist

**Error Message**:
```
[WARNING] No repositories in allowlist. Nothing to do.
```

**Cause**:
The `config/repositories.json` file is empty or doesn't exist.

**Solution**:
1. Create/edit `config/repositories.json`:
   ```json
   {
     "repositories": [
       "juninmd/project1",
       "juninmd/project2"
     ]
   }
   ```

2. Commit and push the changes

**Note**: This only affects Product Manager, Interface Developer, and Senior Developer agents. PR Assistant works on **all repositories** regardless of the allowlist.

---

### ❌ JULES_API_KEY not set

**Error Message**:
```
ValueError: JULES_API_KEY environment variable is required
```

**Solution**:
Add `JULES_API_KEY` to GitHub Secrets:
1. Go to Settings → Secrets and variables → Actions
2. Add secret: `JULES_API_KEY`
3. Value: Your Jules API key

See [SECRETS_SETUP.md](SECRETS_SETUP.md) for detailed instructions.

---

### ❌ Workflow not running on schedule

**Possible Causes**:
1. Workflows disabled (check Actions tab)
2. Repository inactive (GitHub disables scheduled workflows after 60 days of inactivity)
3. Invalid cron expression

**Solution**:
1. Check if Actions are enabled (Settings → Actions → Allow all actions)
2. Manually trigger workflow once to reactivate scheduled runs
3. Verify cron expression syntax

---

### ❌ Permission denied errors

**Error Message**:
```
Error: Resource not accessible by integration
```

**Solution**:
Ensure workflows have proper permissions:
```yaml
permissions:
  contents: write
  pull-requests: write
  issues: write
```

And use `GH_PAT` as described above.

---

## Getting Help

If you encounter issues not listed here:

1. **Check logs**:
   - Go to Actions tab
   - Click on failed workflow run
   - Review detailed logs

2. **Check secrets**:
   - Settings → Secrets and variables → Actions
   - Verify all required secrets are set

3. **Check permissions**:
   - Verify repository settings allow Actions
   - Check if branch protection rules interfere

4. **Manual testing**:
   ```bash
   # Test locally
   uv run run-agent pr-assistant
   ```

5. **Open an issue** on GitHub with:
   - Error message
   - Workflow logs
   - Steps to reproduce
