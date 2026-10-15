# Project Health

This document records the repository improvement pass applied on 2026-05-17.

## Detected Surface

- Python pyproject
- Python requirements
- uv lockfile
- Docker
- GitHub Actions

## Automation Added Or Confirmed

- Security policy: Already present before this pass.
- Dependabot: Already present before this pass.
- EditorConfig: Already present before this pass.
- Project Health workflow: Existing workflows were present; added a dedicated Project Health workflow.
- Pull request quality checklist: Added in this pass.

## Available Root Commands

- No root package scripts detected.

## Improvement Plan

1. Keep dependency drift visible through weekly Dependabot pull requests.
2. Keep runtime secrets out of git through the Project Health guardrail.
3. Use .editorconfig to reduce formatting churn across agents and local editors.
4. Treat this file as the lightweight audit entry for future improvements.

## Suggested Next Improvements

- Add project-specific tests to the Project Health workflow once the default branch is stable.
- Add CodeQL or language-native security scanning where the repository has a supported build path.
- Convert manual setup notes into reproducible scripts when setup steps are repeated.
- Add structured logging and health endpoints to service repositories that expose long-running APIs.

## LLM-Assisted Improvement Pass (2026)

Applied on the default branch (`master`):

- **Configuration**: `src/config/settings.py` is now the single source of truth for
  `DEFAULT_LITELLM_API_BASE` and `DEFAULT_OLLAMA_MODEL`; agents import these instead
  of repeating literals. `review_workspace.litellm_base()` no longer defaults to a
  different, cluster-internal URL.
- **Docs/code parity**: `.env.example` documented `ENABLE_*` toggles that settings.py
  never read; the file now lists the real names (including `CODE_REVIEWER_ENABLED`)
  and a regression test fails if they drift again.
- **Attribution**: the AGENTS.md origin footer is emitted exclusively through
  `src/agents/utils.py::build_origin_metadata` (code_reviewer, interface_developer,
  pr_sla no longer inline it).
- **Logging**: `src/config/repository_allowlist.py` uses the structured logger instead
  of `print()`.
- **Known gap**: several modules still exceed the 150-line guideline; splitting them
  requires touching many test patch targets and is tracked in `ROADMAP.md`.