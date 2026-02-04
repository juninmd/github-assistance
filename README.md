# Pull Request Assistance Agent

This repository contains an intelligent agent that manages Pull Requests for **juninmd**, specifically targeting PRs from `google-labs-jules`.

## Features
- **Auto-Merge**: Merges clean, passing PRs.
- **Conflict Resolution**: Uses Gemini AI to resolve merge conflicts autonomously.
- **Pipeline Monitoring**: Requests corrections if CI fails.
- **Multi-Repo Support**: Scans all repositories owned by `juninmd`.
- **AI Integration**: Supports Google Gemini (Production) and Ollama (Local/Dev).

## Rules for Jules da Google (google-labs-jules)

The agent strictly follows these rules for Pull Requests opened by `google-labs-jules`:

1.  **Conflict Resolution**: If merge conflicts exist, the agent resolves them autonomously by cloning the repo, fixing the conflict using AI, and pushing the changes to the same branch.
2.  **Pipeline Issues**: If tests or build fail, the agent comments on the PR requesting corrections.
3.  **Auto-Merge**: If the PR is clean (no conflicts) and passes all pipeline checks, it is automatically merged.

## Setup

1. Install `uv`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Set Environment Variables:
   - `GITHUB_TOKEN`: Your GitHub Personal Access Token.
   - `GEMINI_API_KEY`: Google Gemini API Key.

## Usage

Run the agent:
```bash
uv run pr-assistant
```

## Testing

Run tests with coverage:
```bash
uv run pytest --cov=src tests/
```

## Agents.md
See `AGENTS.md` for specific rules regarding "Jules da Google".
