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

## `benchmark.py`

Micro-benchmarks for the durable queue, the webhook API and CLI cold start.
`--out file.json` measures the current checkout; `--compare base.json head.json`
prints a markdown table. Method and latest results: [docs/BENCHMARK.md](../docs/BENCHMARK.md).

## `seed_demo_queue.py`

Creates a throwaway SQLite queue with deterministic demo data to explore the
dashboard locally (`--db /tmp/demo/webhooks.db`). Refuses to run on a database
that already has jobs.
