# Github Assistance

[![CI/CD Pipeline](https://github.com/juninmd/github-assistance/actions/workflows/validate.yml/badge.svg)](https://github.com/juninmd/github-assistance/actions/workflows/validate.yml)
[![codecov](https://codecov.io/gh/juninmd/github-assistance/branch/master/graph/badge.svg)](https://codecov.io/gh/juninmd/github-assistance)
[![Gitleaks](https://img.shields.io/badge/secret_scanning-gitleaks-blue.svg)](https://github.com/juninmd/github-assistance/actions/workflows/security.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/linter-ruff-purple.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/type_checker-pyright-yellow.svg)](https://github.com/microsoft/pyright)

A fleet of AI agents that maintains a GitHub portfolio on autopilot: it merges
and fixes pull requests, scans for leaked secrets, keeps dependencies and
READMEs fresh, cleans stale branches and delegates larger coding work to
[Jules](https://jules.google) or [opencode](https://opencode.ai).

Agent personas, rules and the interaction protocol live in [AGENTS.md](AGENTS.md).
The durable queue, merge policy and operations are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Agents

17 agents are registered in `src/agents/registry.py` and run through one CLI:

| Agent | What it does |
|---|---|
| `pr-assistant` | Reviews PRs, resolves comments, fixes CI, updates branches and squash-merges when the safe-merge policy allows |
| `conflict-resolver` | Finds PRs with merge conflicts and resolves them with AI |
| `code-reviewer` | AI review of PRs for quality, bugs and security |
| `ci-health` | Monitors pipelines, detects failures and triggers remediation |
| `pr-sla` | Tracks PR age and review time, flags stale PRs |
| `security-scanner` | Gitleaks secret scanning plus the no-cron-workflow policy |
| `secret-remover` | Classifies findings and purges real secrets from git history |
| `dependency-manager` | Opens one grouped, tested PR with security and patch/minor updates |
| `readme-curator` | Rewrites missing, old (>6 months) or low-scoring READMEs |
| `intelligence-standardizer` | Enforces `AGENTS.md` / `.agents/` across repositories |
| `senior-developer` | Repository analysis and improvement tasks |
| `product-manager` | Roadmaps and feature planning |
| `interface-developer` | UI/UX and accessibility tasks |
| `project-creator` | Scaffolds new projects from generated ideas |
| `branch-cleaner` | Deletes branches already merged into the default branch |
| `jules-tracker` | Tracks Jules sessions; answers questions and approves plans via LLM |
| `jules-cleaner` | Deletes Jules sessions older than the retention window |

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                      # install dependencies
cp .env.example .env         # fill in GITHUB_TOKEN, JULES_API_KEY, AI keys...

uv run run-agent pr-assistant                       # run one agent
uv run run-agent pr-assistant --pr owner/repo#42    # target a single PR
uv run run-agent readme-curator --ai-provider gemini --ai-model gemini-2.5-flash
uv run run-agent all                                # all enabled agents, in dependency order
```

Each agent also has its own entry point (`uv run security-scanner`, ...).
Results are written to `results/*.json` and summarized on Telegram.

## Configuration

Everything is read from environment variables (see `.env.example` and
`src/config/settings.py`).

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` / `GH_PAT` | GitHub access (a GitHub App is also supported) |
| `GITHUB_OWNER` | Account whose repositories are managed |
| `JULES_API_KEY` | Jules API |
| `ENABLE_AI`, `AI_PROVIDER`, `AI_MODEL` | AI on/off and model (`gemini`, `openai`, `ollama`, `litellm`) |
| `*_ENABLED` (e.g. `PR_ASSISTANT_ENABLED`) | Per-agent toggles used by `run-agent all` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Notifications |
| `CONFLICT_OPENCODE_ENABLED`, `PIPELINE_FIX_ENABLED` | Opt-in opencode conflict / CI fixing |
| `JULES_CLEANER_MAX_AGE_DAYS` | Jules session retention (default 3) |
| `AUTOMATION_MODE`, `SIMULATION_MODE` | `observe` vs `autonomous`; dry-run all writes |

Repository scope is controlled by `config/repositories.json` (allowlist) and
per-repo autonomy (`observe | suggest | fix | merge`) by `config/autonomy.json`.

## Durable automation core

GitHub webhooks hit a FastAPI server (`webhook-server`), are persisted
atomically in SQLite and processed by a worker with leases, retries and
idempotency (`queue-worker`). Merges go through a single non-bypassable policy:
every check on the current head SHA must be green, and the SHA is re-validated
right before merging. Inspect decisions with `pr-insight explain --pr owner/repo#N`
or `GET /api/prs/{owner}/{repo}/{number}/explain`. Full details, commands and
limits (single-replica SQLite writer) are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Deployment

The `Dockerfile` bundles Python, Node.js, `opencode` and `gitleaks`, runs as a
non-root user under `tini`, and defaults to `run-agent pr-assistant`. Periodic
agents (including all Jules routines) run as Kubernetes CronJobs/Jobs; GitHub
Actions is used for CI and policy checks only. This repository intentionally
has **no cron workflows** (enforced by `scripts/check_no_cron_workflows.py`).

## Development

```bash
uv run ruff check . && uv run ruff format --check .   # lint / format
uv run pyright                                        # types
uv run pytest --cov                                   # tests (coverage gate: 80%)
./scripts/lint.sh                                     # lint + types, as CI does
```

CI (`validate.yml`) calls the shared `base-actions` validation, then runs a
committed-secrets check, `uv lock --check`, Ruff, Pyright, the smoke tests and
the no-cron guard. `security.yml` runs the shared security scan (Gitleaks) and
`deploy.yml` builds and pushes the Docker image to GHCR.
Code standards (150-line files, strict typing, DRY/KISS/SOLID, squash merge) are
described in [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Project layout

```
src/agents/       one folder per agent (agent.py + instructions.md)
src/queue/        durable SQLite job queue and worker
src/webhooks/     FastAPI webhook server
src/insight/      PR decision explanations (CLI + API)
src/jules/        Jules API client
src/ai/           Gemini / OpenAI / Ollama / LiteLLM clients
src/config/       settings, allowlist, autonomy and priorities
config/           repositories.json, autonomy.json, opencode.json
docs/             ARCHITECTURE.md, PROJECT_HEALTH.md
scripts/ tools/   maintenance and dry-run utilities
```

See also [ROADMAP.md](ROADMAP.md), [SECURITY.md](SECURITY.md) and [REFERENCES.md](REFERENCES.md).
