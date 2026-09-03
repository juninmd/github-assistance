# Standardizing {{repository_name}} Intelligence System

## Objective
Implement the "Intelligence System" (AGENTS.md and .agents folder) into the repository. This is critical for agent-to-agent collaboration and long-term project maintainability.

## Structure 🏗️
1. **Root**: Create an `AGENTS.md` file. Use the `github-assistance` AGENTS.md as a template for style, but tailor the content to the specific agents and personas of this project.
2. **Directory**: Create a `.agents/` directory with the following structure:
   - `skills/`: Individual .md files for specific technical capabilities.
   - `agents/`: Descriptions of the personas used.
   - `rules/`: Project-specific constraints and global rules.
   - `workflows/`: Step-by-step guides for common operations (e.g., /deploy, /test).
3. **CI/CD**: Validation runs on the Kubernetes cluster (CronJobs/Jobs) — GitHub Actions is prohibited. Ensure local validation scripts (`lint`, `build`, `dev`) exist in `scripts/` so the cluster job can invoke them.

## Core Principles 💎
You MUST enforce these in all subsequent edits:
- **KISS (Keep It Simple, Stupid)**: Prioritize readability and simplicity.
- **YAGNI (You Aren't Gonna Need It)**: Do not add code for features that aren't currently required.
- **DRY (Don't Repeat Yourself)**: Eliminate redundancy.
- **SRP (Single Responsibility Principle)**: Each class/function should have one reason to change.
- **Max 180 lines per file**: If a file exceeds this, refactor it into smaller, logical modules.

## Validation 🧪
- After making a change, check for common development scripts: `lint`, `build`, `dev`.
- If they exist, run them to ensure the project stays healthy.
- If they don't exist, recommend creating them.

{{#if missing_agents_md}}
You are missing the root `AGENTS.md`. This is priority #1.
{{/if}}

{{#if missing_standard_workflow}}
You are missing local validation scripts (e.g. `scripts/lint.sh`, `scripts/test.sh`).
- Create them (ruff, pyright, pytest, gitleaks) so the cluster validation Job can run them on push.
- ⛔ **NEVER create GitHub Actions workflows** (`.github/workflows/`). GitHub Actions is prohibited — all validation and periodic work runs on the Kubernetes cluster.
- Example `scripts/lint.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
uv run ruff check .
uv run pyright
uv run pytest tests/ --ignore=tests/smoke
```
{{/if}}

{{#if missing_contributing}}
You are missing `CONTRIBUTING.md`.
- Create it based on standard practices.
- Include sections for: Getting Started, Development Environment, Code Style (ruff), and Testing (pytest).
{{/if}}

{{#if missing_license}}
You are missing a `LICENSE` file.
- Create an MIT License file (unless you find evidence of another license).
- Use "Juninmd" as the holder.
{{/if}}

Go!
