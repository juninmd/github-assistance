# Github Assistance

[![CI/CD Pipeline](https://github.com/juninmd/github-assistance/actions/workflows/validate.yml/badge.svg)](https://github.com/juninmd/github-assistance/actions/workflows/validate.yml)
[![codecov](https://codecov.io/gh/juninmd/github-assistance/branch/master/graph/badge.svg)](https://codecov.io/gh/juninmd/github-assistance)
[![Gitleaks](https://img.shields.io/badge/secret_scanning-gitleaks-blue.svg)](https://github.com/juninmd/github-assistance/actions/workflows/security.yml)
[![Bun](https://img.shields.io/badge/runtime-bun-black.svg)](https://bun.sh)
[![TypeScript](https://img.shields.io/badge/lang-typescript-blue.svg)](https://www.typescriptlang.org)

A fleet of AI agents that maintains a GitHub portfolio on autopilot: it merges
and fixes pull requests, scans for leaked secrets, keeps dependencies and
READMEs fresh, cleans stale branches and delegates larger coding work to
[opencode](https://opencode.ai).

Agent personas, rules and the interaction protocol live in [AGENTS.md](AGENTS.md).
The durable queue, merge policy and operations are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Agents

17 agents are declared in one table, `ts/src/agents/catalog.ts`, and run through one CLI:

| Agent | What it does |
|---|---|
| `pr-assistant` | Reviews PRs, resolves comments, fixes CI, updates branches and squash-merges when the safe-merge policy allows |
| `conflict-resolver` | Finds PRs with merge conflicts and resolves them with AI |
| `code-reviewer` | AI review of PRs for quality, bugs and security; non-blocking tips on outdated stack/libs and README drift (`REVIEW_ADVISORIES=false` to disable) |
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

## Quick start

Requires [Bun](https://bun.sh) 1.4+ (Node.js is only needed on the host that runs `build_check`/`conflict-resolver` against `npm` repos).

```bash
cd ts && bun install         # install dependencies
cp ../.env.example ../.env   # fill in GITHUB_TOKEN, AI keys...

bun src/cli/run-agent.ts pr-assistant                       # run one agent
bun src/cli/run-agent.ts pr-assistant --pr owner/repo#42    # target a single PR
bun src/cli/run-agent.ts readme-curator --ai-provider gemini --ai-model gemini-2.5-flash
bun src/cli/run-agent.ts all                                # all enabled agents, in dependency order
```

Results are written to `results/*.json` and summarized on Telegram.

## Dashboard

The webhook server ships a control-room UI at `/dashboard/` — queue health,
outcome charts, a searchable job table with a detail drawer (reprocess, explain
why a PR was not merged) and the agent fleet. It is plain HTML/CSS/ES modules
(no build step, no CDN, strict CSP) and reads `/api/*` with `ADMIN_API_TOKEN`.

![Control-room dashboard](docs/assets/dashboard/overview-light.png)

```bash
# Try it locally with deterministic demo data
bun ts/scripts/seed-demo-queue.ts --db /tmp/demo/webhooks.db
ADMIN_API_TOKEN=demo WEBHOOK_DATABASE_PATH=/tmp/demo/webhooks.db WORKER_ENABLED=false \
  GITHUB_TOKEN=x bun ts/src/webhooks/server.ts   # http://localhost:8080/dashboard/ (token: demo)
```

Performance evidence and how to reproduce it: [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Configuration

Everything is read from environment variables (see `.env.example` and
`ts/src/config/settings.ts`).

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` / `GH_PAT` | GitHub access (a GitHub App is also supported) |
| `GITHUB_OWNER` | Account whose repositories are managed |
| `ENABLE_AI`, `AI_PROVIDER`, `AI_MODEL` | AI on/off and model (`gemini`, `openai`, `ollama`, `litellm`) |
| `*_ENABLED` (e.g. `PR_ASSISTANT_ENABLED`) | Per-agent toggles used by `run-agent all` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Notifications |
| `CONFLICT_OPENCODE_ENABLED`, `PIPELINE_FIX_ENABLED` | Opt-in opencode conflict / CI fixing |
| `AUTOMATION_MODE`, `SIMULATION_MODE` | `observe` vs `autonomous`; dry-run all writes |

Repository scope is controlled by `config/repositories.json` (allowlist) and
per-repo autonomy (`observe | suggest | fix | merge`) by `config/autonomy.json`.

## Durable automation core

GitHub webhooks hit a FastAPI server (`webhook-server`), are persisted
atomically in SQLite and processed by a worker with leases, retries and
idempotency (`queue-worker`). Merges go through a single non-bypassable policy:
every check on the current head SHA must be green, and the SHA is re-validated
right before merging. Inspect decisions with `bun ts/src/cli/insight.ts explain --pr owner/repo#N`
or `GET /api/prs/{owner}/{repo}/{number}/explain`. Full details, commands and
limits (single-replica SQLite writer) are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Deployment

The `Dockerfile` bundles Bun, Node.js, `opencode` and `gitleaks`, runs as a
non-root user under `tini`, and defaults to `run-agent pr-assistant`. Periodic
agents run as Kubernetes CronJobs/Jobs; GitHub
Actions is used for CI and policy checks only. This repository intentionally
has **no cron workflows** (enforced by `ts/scripts/check-no-cron.ts`).

## Development

```bash
cd ts
bun run typecheck   # tsc --noEmit (strict)
bun test            # bun:test
```

CI (`validate.yml`) calls the shared `base-actions` validation, then runs a
committed-secrets check, `tsc --noEmit`, `bun test` and the no-cron guard. `security.yml` runs the shared security scan (Gitleaks) and
`deploy.yml` builds and pushes the Docker image to GHCR.
Code standards (150-line files, strict typing, DRY/KISS/SOLID, squash merge) are
described in [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Project layout

```
ts/src/agents/    one folder per agent (agent.ts + instructions.md)
ts/src/queue/     durable SQLite job queue and worker (bun:sqlite)
ts/src/webhooks/  Bun.serve webhook server + admin API
ts/src/insight/   PR decision explanations (CLI + API)
ts/src/ai/        Gemini / OpenAI / Ollama / LiteLLM clients
ts/src/config/    settings, allowlist, autonomy and priorities
ts/static/        dashboard (no build step)
ts/scripts/       maintenance and dry-run utilities
config/           repositories.json, autonomy.json, opencode.json
docs/             ARCHITECTURE.md, PROJECT_HEALTH.md
```

See also [ROADMAP.md](ROADMAP.md), [SECURITY.md](SECURITY.md) and [REFERENCES.md](REFERENCES.md).
