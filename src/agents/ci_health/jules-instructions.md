# Fix CI pipeline for {{repository}}

The Continuous Integration (CI) workflow for this repository has been failing in the last 24 hours. Your goal is to **fix the pipeline so it passes reliably on the default branch** and create a Pull Request with the necessary changes.

## Context

{{failures}}

## Goals

- Investigate why the workflow fails and identify the root cause.
- Apply minimal, focused changes to make the CI pass.
- Prefer fixing tests, workflows, or configuration rather than disabling checks.
- If missing secrets or configuration values are required, document what is needed and include a safe fallback if possible.

## Deliverables

- A PR that fixes the CI pipeline.
- A short summary in the PR description explaining the fix and how to verify it.
