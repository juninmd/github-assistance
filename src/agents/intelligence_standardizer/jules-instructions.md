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
3. **CI/CD**: Ensure the repository uses the centralized GitHub Actions from `juninmd/github-actions-base`.

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
You are missing the `.github/workflows/standard.yml`.
- Create it to call the reusable workflows from `juninmd/github-actions-base`.
- It MUST include `gitleaks`, `commit-lint`, and optionally `node-ci` (if Node.js) and `release` (if master/main).
- Example:
```yaml
name: Standard CI/CD
on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  gitleaks:
    uses: juninmd/github-actions-base/.github/workflows/gitleaks.yml@main
  commit-lint:
    uses: juninmd/github-actions-base/.github/workflows/commit-lint.yml@main
  build:
    uses: juninmd/github-actions-base/.github/workflows/node-ci.yml@main
  release:
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master'
    needs: [build, gitleaks]
    uses: juninmd/github-actions-base/.github/workflows/release.yml@main
    secrets: inherit
```
{{/if}}

Go!
