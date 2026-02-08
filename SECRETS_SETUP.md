# GitHub Secrets Configuration Guide

This guide will help you set up the required secrets for the Development Team Agents.

## Required Secrets

### 1. JULES_API_KEY

**Value**: `AQ.Ab8RN6I2K0-WGNo9DnoRQOV2mmq_6Cv-4XpMpPpOjXUOdWADuQ`

**How to add**:
1. Go to your GitHub repository
2. Click on **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `JULES_API_KEY`
5. Value: Paste the API key above
6. Click **Add secret**

### 2. GEMINI_API_KEY (Required for PR Assistant)

**How to get**:
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy the key

**How to add**:
1. Go to your GitHub repository
2. Click on **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `GEMINI_API_KEY`
5. Value: Paste your Gemini API key
6. Click **Add secret**

### 3. GITHUB_TOKEN

This is **automatically provided** by GitHub Actions. You don't need to add it manually.

## Optional Secrets

### TELEGRAM_BOT_TOKEN (For notifications)

**How to get**:
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow instructions
3. Copy the token provided

**How to add**:
1. Go to your GitHub repository
2. Click on **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `TELEGRAM_BOT_TOKEN`
5. Value: Paste your bot token
6. Click **Add secret**

### TELEGRAM_CHAT_ID (For notifications)

**How to get**:
1. Send a message to your bot on Telegram
2. Open: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find your chat ID in the response

**How to add**:
1. Go to your GitHub repository
2. Click on **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `TELEGRAM_CHAT_ID`
5. Value: Paste your chat ID
6. Click **Add secret**

## Verification

After adding all secrets, you should see them listed in:
**Settings** → **Secrets and variables** → **Actions** → **Repository secrets**

Required secrets:
- ✅ JULES_API_KEY
- ✅ GEMINI_API_KEY

Optional secrets:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

## Security Notes

⚠️ **IMPORTANT**:

1. **Never commit secrets** to the repository
2. **Never share secrets** publicly
3. **Rotate secrets** periodically (recommended: every 90 days)
4. **Use different secrets** for different environments
5. **Check .gitignore** to ensure it blocks secret files

## Testing Secrets

To test if secrets are configured correctly:

1. Go to **Actions** tab
2. Select any workflow (e.g., "Product Manager Agent")
3. Click **Run workflow**
4. Select branch: `main`
5. Click **Run workflow**
6. Monitor the workflow run for any authentication errors

If you see errors like "API key is required", check that the secret is:
- Correctly named (exact spelling, case-sensitive)
- Has the correct value (no extra spaces)
- Is accessible to the workflow

## Troubleshooting

### "JULES_API_KEY environment variable is required"

**Solution**: Add the `JULES_API_KEY` secret as described above.

### "401 Unauthorized" from Jules API

**Solutions**:
1. Verify the API key is correct
2. Check if the API key has expired
3. Ensure there are no extra spaces in the secret value
4. Try regenerating the API key

### "GITHUB_TOKEN" issues

**Solutions**:
1. Ensure workflow has proper permissions
2. Check repository settings → Actions → General → Workflow permissions
3. Select "Read and write permissions"

### Workflow doesn't trigger

**Solutions**:
1. Ensure workflows are enabled in repository settings
2. Check workflow YAML syntax
3. Verify cron schedule is correct
4. Check if repository has required secrets

## Support

If you encounter issues:
1. Check GitHub Actions logs
2. Review secret names for typos
3. Verify secret values are correct
4. Open an issue with error details

---

**Last Updated**: February 8, 2026
**Version**: 1.0.0
