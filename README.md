# Github Assistance

[![codecov](https://codecov.io/gh/juninmd/github-assistance/branch/main/graph/badge.svg)](https://codecov.io/gh/juninmd/github-assistance)
[![Gitleaks](https://img.shields.io/badge/secret_scanning-gitleaks-blue.svg)](https://github.com/juninmd/github-assistance)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/linter-ruff-purple.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/type_checker-pyright-yellow.svg)](https://github.com/microsoft/pyright)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()
[![Protocol: Antigravity](https://img.shields.io/badge/Protocol-Antigravity-orange.svg)]()

> A modern, high-performance project built with **Python 3.12+**. Orchestrated under the Antigravity protocol.

## Features

- **High Performance**: Optimized for speed and low resource usage.
- **Clean Architecture**: Built following strict Antigravity guidelines.
- **Automated CI/CD**: Multi-stage pipeline with linting, type checking, testing, security scanning, and deployment.
- **AI Agent Fleet**: 15 autonomous agents that maintain the GitHub portfolio (security, PRs, CI, docs, roadmaps).

## 🤖 AI Agents

This repository is an orchestration platform for **autonomous AI agents** that maintain the
GitHub portfolio (`juninmd`). Every agent inherits `BaseAgent`, runs via the `run-agent` CLI,
and delegates coding work to Jules or OpenCode sessions.

> **Execution rules (non-negotiable)**: all AI traffic goes through the OpenAI-compatible
> LiteLLM proxy on the Kubernetes cluster; **nothing runs on GitHub Actions** — all
> periodic/event-driven work runs on cluster CronJobs/Jobs; no generated code may create
> GitHub Actions cron workflows.

| Agent | Role | Status |
|---|---|---|
| Senior Developer | Repo analysis and task creation (features, security, CI/CD, tech debt, modernization, performance) | ✅ Weekly (Sun 02:00 UTC) |
| Security Scanner | Gitleaks scan of all repos + sanitized reports (no secret values) | ✅ Daily (06:00 UTC) |
| Secret Remover | AI classification and remediation of leaked credentials | ✅ Daily (06:30 UTC, if needed) |
| PR Assistant | Auto-merge, conflict resolution, pipeline fixing across **all** repos | ✅ Every 15 min |
| Project Creator | New private repo scaffolding + Jules development session | ✅ Weekly (Sun 00:00 UTC) |
| Jules Tracker | Unblocks Jules sessions, answers questions, plan approval via LiteLLM | ✅ Cluster CronJob |
| Jules Cleaner | Deletes Jules sessions older than the retention window (2 days) | ✅ Cluster CronJob |
| Code Reviewer | AI review of open PRs (bugs, security, performance, best practices) | ⏸️ On-demand |
| CI Health | Monitors workflow failures and remediates pipelines | ⏸️ On-demand |
| PR SLA | Alerts on stale PRs (>24h without activity) | ⏸️ On-demand |
| Branch Cleaner | Deletes branches already merged into the main branch | ⏸️ On-demand |
| Product Manager | Roadmap generation and feature prioritization | ⏸️ On-demand |
| Interface Developer | UI/UX analysis and improvement issue creation | ⏸️ On-demand |
| Intelligence Standardizer | Enforces `AGENTS.md` + `.agents/` structure across repositories | ⏸️ On-demand |
| Readme Curator | Creates/improves README documentation | ⏸️ On-demand |

> Full personas, interaction protocol and orchestration rules live in [`AGENTS.md`](AGENTS.md).
> Run any agent manually with: `uv run run-agent <name>`.

## CI/CD Pipeline

All CI/CD stages run on the **Kubernetes cluster** (CronJobs/Jobs triggered by schedule or the
webhook receiver) — nothing executes on GitHub Actions:

| Stage | Tools | Description |
|---|---|---|
| Lint | Ruff | Code formatting and linting |
| Type Check | Pyright | Static type checking |
| Security | Bandit, pip-audit, Gitleaks | SAST and dependency vulnerability scanning |
| Test | Pytest, pytest-cov | Unit/integration tests with coverage reporting |
| Build | uv | Package building and artifact generation |
| Deploy | kaniko (cluster) | Container image build and push to GHCR |

## Quality Gates

- **Linting**: Ruff with pycodestyle, pyflakes, isort, pyupgrade, and bandit-security rules
- **Type Safety**: Pyright in basic mode with strict import checking
- **Security**: Bandit SAST scanning + pip-audit dependency auditing + Gitleaks secret scanning
- **Coverage**: Test coverage reported to Codecov (80%+ target)
- **Dependencies**: explicit audit commands and targeted dependency fixes; no Dependabot automation

## Tech Stack

- **Primary Technology**: Python 3.12+
- **Architecture**: Modular and domain-driven.
- **Package Manager**: uv (fast Python package installer)

## Antigravity Protocol

This project follows the **Antigravity** code standards:
- **150-Line Limit**: Applied to all logic modules.
- **Strict Typing**: Avoiding dynamic/any types.
- **Clean Code**: DRY, KISS, and SOLID principles applied rigorously.

---

*"Simplicity is the ultimate sophistication."*
