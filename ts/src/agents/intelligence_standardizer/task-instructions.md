# Standardizing {{repository_name}} Intelligence System

## Objective
Implement the "Intelligence System" (AGENTS.md and .agents folder) into the repository. This is critical for agent-to-agent collaboration and long-term project maintainability.

## Structure 🏗️
1. **Root**: Create a short `AGENTS.md`. Write only facts an agent would otherwise get wrong in this repository:
   package manager, exact build/test/lint commands, deploy constraints, directories that must not be touched.
   Do not restate generic advice ("follow best practices") and do not copy the global rules: link to them instead —
   the owner's global instructions live at https://github.com/juninmd/skills/blob/master/.agents/AGENTS.md and the
   skills at https://github.com/juninmd/skills.
2. **Directory**: Create a `.agents/` directory with `rules/` (project-specific constraints only) and, when useful,
   `workflows/` (step-by-step guides for operations such as deploy or release).
3. **CI/CD**: Ensure the repository uses the centralized GitHub Actions from `juninmd/base-actions`.

## Validation 🧪
- Read the repository before writing: every command you document must exist (package.json scripts, Makefile, etc.).
- Run the existing lint/build/test scripts, if any, to ensure the project stays healthy.
- Change documentation and config only; never change application code in this task.

{{#if missing_agents_md}}
You are missing the root `AGENTS.md`. This is priority #1.
{{/if}}

{{#if missing_standard_workflow}}
You are missing the `.github/workflows/standard.yml`.
- Create it to call the reusable workflows from `juninmd/base-actions`.
- It MUST include `security-scan` (which covers gitleaks), `commit-lint`, and optionally `node-ci` (if Node.js) and `release` (if master/main).
- Example:
```yaml
name: Standard CI/CD
on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  security-scan:
    uses: juninmd/base-actions/.github/workflows/reusable-security-scan.yml@main
  commit-lint:
    uses: juninmd/base-actions/.github/workflows/reusable-commit-lint.yml@main
  build:
    uses: juninmd/base-actions/.github/workflows/reusable-node-ci.yml@main
  release:
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master'
    needs: [build, security-scan]
    uses: juninmd/base-actions/.github/workflows/reusable-release.yml@main
    secrets: inherit
```
{{/if}}

{{#if missing_contributing}}
You are missing `CONTRIBUTING.md`.
- Create it based on standard practices.
- Include sections for: Getting Started, Development Environment, Code Style and Testing, using the repository's own stack and commands.
{{/if}}

{{#if missing_license}}
You are missing a `LICENSE` file.
- Create an MIT License file (unless you find evidence of another license).
- Use "Juninmd" as the holder.
{{/if}}

Go!
