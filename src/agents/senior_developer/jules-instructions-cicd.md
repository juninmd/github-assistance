# Task: CI/CD Pipeline Setup for {{repository}}

## Identified Improvements
{{improvements}}

## CI/CD Requirements

> ⛔ **PROHIBITED — GitHub Actions.** Never create `.github/workflows/`
> workflows, and never add `on: schedule:` / `- cron:`. Nothing runs on GitHub
> Actions. All validation and periodic work runs on the Kubernetes cluster
> (CronJobs/Jobs, triggered by schedule or the webhook receiver). If a job must
> run periodically, delegate it to the central cluster orchestrator.

### 1. Local Validation Scripts
Create `scripts/lint.sh` (and `scripts/test.sh` if absent) so the cluster
validation Job can invoke them on push:

```bash
#!/usr/bin/env bash
set -euo pipefail
# Add language-specific commands, e.g.:
# uv run ruff check . && uv run pyright && uv run pytest tests/
```

Do **NOT** create any `.github/workflows/` file.

### 2. Testing Requirements
- [ ] Minimum 80% code coverage
- [ ] Unit tests for all business logic
- [ ] Integration tests for API endpoints
- [ ] E2E tests for critical user flows
- [ ] Test reports generated and uploaded

### 3. Quality Gates
- [ ] Linting (ESLint/Pylint/equivalent)
- [ ] Type checking (TypeScript/mypy)
- [ ] Code formatting (Prettier/Black)
- [ ] Security scanning (Snyk/SAST tools)
- [ ] Dependency vulnerability checks

### 4. Build Process
- [ ] Optimize build artifacts
- [ ] Generate source maps (for debugging)
- [ ] Minification and bundling
- [ ] Asset optimization (images, fonts)
- [ ] Build artifact versioning

### 5. Deployment Strategy
- [ ] Automated deployment to staging on PR merge
- [ ] Manual approval for production deployment
- [ ] Rollback capability
- [ ] Health checks post-deployment
- [ ] Deployment notifications

### 6. Monitoring & Alerts
- [ ] Build status badges in README
- [ ] Slack/Email notifications on failures
- [ ] Performance monitoring integration
- [ ] Error tracking (Sentry/similar)

### 7. Documentation
- [ ] Update README with badge and build instructions
- [ ] Document deployment process
- [ ] Add CONTRIBUTING.md with CI/CD guidelines
- [ ] Environment variables documentation

## Language-Specific Additions

### For Node.js/JavaScript
- Use `package-lock.json` or `yarn.lock`
- Cache `node_modules` in CI
- Run `npm audit`

### For Python
- Use `requirements.txt` with pinned versions
- Cache pip dependencies
- Run `safety check` or `pip-audit`

### For Go
- Use Go modules
- Run `go vet` and `golangci-lint`

### For Java
- Use Maven/Gradle with dependency locking
- Run SpotBugs/PMD

## Success Criteria
- All CI/CD stages pass
- Documentation complete
- Build time < 10 minutes
- All quality gates enforced
- PR with detailed description of pipeline

Create a comprehensive PR with the complete CI/CD setup.
