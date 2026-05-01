# Contributing to Github Assistance

Welcome! This project uses a fleet of AI agents to automate repository maintenance, security, and development.

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- `uv` (recommended for dependency management)
- GitHub Token with repo scope
- Jules API Key (for agent sessions)
- Telegram Bot Token (optional, for notifications)

### Environment Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Copy `.env.example` to `.env` and fill in your keys.

## 🧠 Developing Agents

All agents should reside in `src/agents/`. Each agent must:
- Inherit from `BaseAgent`.
- Adhere to the **150-line limit** per file.
- Have an `instructions.md` and any necessary `jules-instructions-*.md` templates.
- Maintain 100% test coverage.

### Code Style
We use `ruff` for linting and formatting. Run it before committing:
```bash
uv run ruff check .
uv run ruff format .
```

### Testing
We use `pytest`. Ensure all tests pass:
```bash
uv run pytest
```

## 🛡️ Antigravity Protocol
Follow the rules defined in `AGENTS.md` strictly. Modularity, clean logic, and security are non-negotiable.
