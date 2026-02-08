# Quick Start Guide

Get your automated development team up and running in 5 minutes!

## Prerequisites

- Python 3.12+
- Git
- GitHub account with repository access

## Step 1: Clone the Repository

```bash
git clone https://github.com/juninmd/pull-request-assistance.git
cd pull-request-assistance
```

## Step 2: Install Dependencies

```bash
pip install -e .
```

## Step 3: Configure Secrets

### Option A: Local Development

Create a `.env` file (never commit this!):

```bash
# Required
GITHUB_TOKEN=your_github_token_here
JULES_API_KEY=<your_jules_api_key_here>

# Optional
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

Load environment variables:

```bash
# Linux/Mac
export $(cat .env | xargs)

# Windows PowerShell
Get-Content .env | ForEach-Object {
    $name, $value = $_.split('=')
    Set-Content env:\$name $value
}
```

### Option B: GitHub Actions (Production)

See [SECRETS_SETUP.md](SECRETS_SETUP.md) for detailed instructions.

Quick version:
1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Add secrets:
   - `JULES_API_KEY`: `<your_jules_api_key_here>`
   - `GEMINI_API_KEY`: `<your_gemini_api_key_here>`

## Step 4: Configure Repository Allowlist

Edit `config/repositories.json`:

```json
{
  "repositories": [
    "juninmd/your-project-1",
    "juninmd/your-project-2"
  ]
}
```

## Step 5: Test Run an Agent

```bash
# Test Product Manager Agent
uv run run-agent product-manager

# Test PR Assistant Agent
uv run run-agent pr-assistant
```

Expected output:
```
============================================================
Running Product Manager Agent
============================================================
[ProductManager] [INFO] Starting Product Manager workflow
[ProductManager] [INFO] Analyzing repository: juninmd/your-project
...
Results saved to logs/product-manager-20260208_100000.json
```

## Step 6: Enable GitHub Actions

Commit and push your changes:

```bash
git add config/repositories.json
git commit -m "Configure repository allowlist"
git push origin main
```

The workflows will now run automatically:
- **Product Manager**: Daily at 9:00 AM UTC
- **Interface Developer**: Daily at 11:00 AM UTC
- **Senior Developer**: Daily at 1:00 PM UTC
- **PR Assistant**: Every 30 minutes (all repositories)

## Step 7: Monitor Execution

### Via GitHub Actions UI

1. Go to your repository on GitHub
2. Click **Actions** tab
3. View workflow runs

### Via Log Files

Check the `logs/` directory for execution results:

```bash
ls -lt logs/
```

## Common Commands

```bash
# Run all agents sequentially
uv run run-agent all

# Run specific agent
uv run run-agent product-manager
uv run run-agent interface-developer
uv run run-agent senior-developer
uv run run-agent pr-assistant

# Run tests
pytest tests/

# Run tests with coverage
pytest --cov=src tests/
```

## Verification Checklist

- [ ] Dependencies installed successfully
- [ ] Secrets configured (JULES_API_KEY, GEMINI_API_KEY)
- [ ] Repository allowlist configured
- [ ] Test run completed without errors
- [ ] GitHub Actions workflows enabled
- [ ] First workflow execution successful

## Troubleshooting

### "JULES_API_KEY environment variable is required"
**Solution**: Make sure you've set the environment variable or added the GitHub secret.

### "No repositories in allowlist"
**Solution**: Edit `config/repositories.json` and add your repositories.

### "Could not access repository"
**Solution**: Verify your GITHUB_TOKEN has access to the repositories in the allowlist.

### Workflow not triggering
**Solution**:
1. Check repository **Settings** → **Actions** → **General**
2. Ensure "Allow all actions and reusable workflows" is selected
3. Ensure workflow permissions are set to "Read and write"

## Next Steps

1. **Review execution logs** to see what the agents are doing
2. **Check created PRs** by Jules in your repositories
3. **Monitor agent performance** via GitHub Actions
4. **Customize agent behavior** by modifying their instructions
5. **Add more repositories** to the allowlist

## Getting Help

- 📖 Read the full [README.md](README.md)
- 🏗️ Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- 🔐 Check [SECRETS_SETUP.md](SECRETS_SETUP.md) for secret configuration
- 🐛 Open an issue on GitHub

## Additional Resources

- [Jules API Documentation](https://jules.google/docs/api/reference/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [PyGithub Documentation](https://pygithub.readthedocs.io/)

---

**Ready to automate your development workflow!** 🚀
