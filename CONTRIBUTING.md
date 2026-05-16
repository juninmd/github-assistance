# Contributing to Github Assistance

Welcome! This project uses a fleet of AI agents to automate repository maintenance, security, and development.

## Getting Started

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

## Developing Agents

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

### Type Checking
We use `pyright` for static type checking:
```bash
uv run pyright
```

### Testing
We use `pytest` with coverage. Ensure all tests pass:
```bash
uv run pytest --cov=src tests/
```

### Security Scanning
Run SAST and dependency audits locally:
```bash
uv run bandit -c pyproject.toml -r src
uv run pip-audit
```

## CI/CD Pipeline

This project uses a multi-stage CI/CD pipeline defined in `.github/workflows/ci.yml`:

1. **Lint** - Ruff formatting and lint checks
2. **Type Check** - Pyright static analysis
3. **Security** - Bandit SAST + pip-audit vulnerability scan + Gitleaks secret detection
4. **Test** - Pytest with coverage, uploaded to Codecov
5. **Build** - Package build with hatchling via uv
6. **Deploy** - Docker image build and push (main branch only)

### Pipeline Rules
- All stages must pass before a PR can be merged to `main`.
- Coverage reports are uploaded to Codecov for every PR.
- Security vulnerabilities in dependencies trigger pipeline failure.
- Build artifacts are retained for 7 days.

## Antigravity Protocol
Follow the rules defined in `AGENTS.md` strictly. Modularity, clean logic, and security are non-negotiable.
