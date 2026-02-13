# Scripts

This directory contains utility scripts for development and maintenance.

## lint.sh

Runs code quality checks (linting and type checking).

**Usage:**
```bash
./scripts/lint.sh
```

**What it does:**
1. Runs `ruff` linter on `src/` and `tests/` directories
2. Runs `pyright` type checker on the entire codebase

**Requirements:**
- Project dependencies must be installed (`uv sync --dev`)

**CI Integration:**
This script runs the same checks as the CI workflow, so running it locally before committing can help catch issues early.
