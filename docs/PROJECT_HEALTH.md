# Project Health

This document records the repository improvement pass applied on 2026-05-17.

## Detected Surface

- Python pyproject
- Python requirements
- uv lockfile
- Docker
- Kubernetes cluster (CronJobs/Jobs) — GitHub Actions is prohibited

## Automation Added Or Confirmed

- Security policy: Already present before this pass.
- EditorConfig: Already present before this pass.
- Cluster validation: existing workflows were removed; validation now runs as cluster Jobs (see `scripts/check_no_github_actions.py`).
- Pull request quality checklist: Added in this pass.

## Available Root Commands

- No root package scripts detected.

## Improvement Plan

1. Keep dependency drift visible through weekly Dependabot pull requests.
2. Keep runtime secrets out of git through the Project Health guardrail.
3. Use .editorconfig to reduce formatting churn across agents and local editors.
4. Treat this file as the lightweight audit entry for future improvements.

## Suggested Next Improvements

- Add project-specific tests to the cluster validation Job once the default branch is stable.
- Add gitleaks/SAST scanning to the cluster validation Job where the repository has a supported build path.
- Convert manual setup notes into reproducible scripts when setup steps are repeated.
- Add structured logging and health endpoints to service repositories that expose long-running APIs.