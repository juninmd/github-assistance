# Pull Request Assistance Agent

This repository contains an intelligent agent that manages Pull Requests for **juninmd**, specifically targeting PRs from `google-labs-jules`.

## Features
- **Auto-Merge**: Merges clean, passing PRs.
- **Conflict Resolution**: Uses Gemini AI to resolve merge conflicts autonomously.
- **Pipeline Monitoring**: Requests corrections if CI fails.
- **AI Integration**: Supports Google Gemini (Production) and Ollama (Local/Dev).

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set Environment Variables:
   - `GITHUB_TOKEN`: Your GitHub Personal Access Token.
   - `GEMINI_API_KEY`: Google Gemini API Key.

## Usage

Run the agent:
```python
python -c "from src.agent import Agent; from src.github_client import GithubClient; from src.ai_client import GeminiClient; Agent(GithubClient(), GeminiClient()).run()"
```

## Testing

Run tests with coverage:
```bash
pytest --cov=src tests/
```

## Agents.md
See `AGENTS.md` for specific rules regarding "Jules da Google".
