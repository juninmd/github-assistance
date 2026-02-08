# Task: CI/CD Pipeline Setup for {{repository}}

## Identified Improvements
{{improvements}}

## CI/CD Requirements

### 1. GitHub Actions Workflow
Create `.github/workflows/ci.yml` with:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Linter
        run: # Add language-specific linter

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - name: Run Tests
        run: # Add test command
      - name: Upload Coverage
        uses: codecov/codecov-action@v3

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: # Add build command

  deploy:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy
        run: # Add deployment command
```

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
