## Summary

-

## Quality Checklist

- [ ] Changes are described clearly with context and motivation.
- [ ] Security impact was considered (secrets, auth, data exposure, supply chain).
- [ ] Performance impact was considered (startup, runtime, memory, API calls).
- [ ] Logs, errors, and operational visibility are useful enough to debug failures.
- [ ] Tests added or updated for all new/changed logic (coverage must not decrease).
- [ ] All CI/CD pipeline stages pass (lint, type-check, security, test, build).
- [ ] README or documentation updated if user-facing behavior changed.
- [ ] `uv.lock` is up to date (`uv lock --check` passes).
- [ ] Dependencies are pinned and audited (no new vulnerabilities introduced).

## Verification

- [ ] Tests pass locally: `uv run pytest --cov=src tests/`
- [ ] Linter passes: `uv run ruff check src tests`
- [ ] Type checker passes: `uv run pyright`
- [ ] Formatter passes: `uv run ruff format --check src tests`

---

🤖 **Origem Automatizada**
- **Agente:** `senior_developer`
- **Modelo:** `big-pickle`
- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)