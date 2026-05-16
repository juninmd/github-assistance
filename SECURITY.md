# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

We take the security of github-assistance seriously. If you believe you have found a security vulnerability, please **do not** open a public issue. Instead, report it privately.

### How to Report

1. **Telegram**: Send a direct message to the project maintainer (available via the project's Telegram group)
2. **GitHub Security Advisories**: Use the "Report a vulnerability" feature under the repository's Security tab
3. **Email**: Contact the repository owner directly through GitHub

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (if known)

### What to Expect

- **Acknowledgment**: Within 48 hours of your report
- **Initial Assessment**: Within 5 business days
- **Fix Timeline**: Depends on severity, but typically:
  - Critical: within 24-48 hours
  - High: within 1 week
  - Medium: within 2 weeks
  - Low: within 30 days

## Security Measures

This project implements the following security measures:

### Secret Detection
- **Gitleaks**: Automated scanning of all repositories every 2 days for leaked credentials; also runs on every push/PR to main branch
- **Secret Remover Agent**: AI-powered identification and remediation of real secrets found by gitleaks
- **All findings are sanitized**: Actual secret values are never exposed in reports or logs
- **Comprehensive .gitignore**: Extensive secret exclusion patterns covering API keys, tokens, certificates, GPG/AGE keys, keystores, password databases, Docker/K8s secrets, Terraform state, and more

### SAST & Code Quality
- **CodeQL Analysis**: Weekly GitHub-native semantic code analysis for Python, detecting security vulnerabilities and code quality issues
- **Ruff with Security Rules**: Static analysis using flake8-bandit (S) rules for security linting
- **Pyright Type Checking**: Static type checking to catch type-related issues before runtime

### CI/CD Security
- **Least-privilege permissions**: Each workflow uses minimal GitHub token scopes (read-only where possible)
- **Dependency vulnerability scanning**: `pip-audit` runs in CI to detect known vulnerabilities in dependencies
- **Lockfile verification**: `uv lock --check` ensures lockfile is up-to-date with pyproject.toml
- **SAST scanning**: Static analysis via ruff with security-focused rule sets (bandit S rules)
- **Automated dependency updates**: Dependabot configured for pip, Docker, and GitHub Actions
- **No secrets in code**: All sensitive values via environment variables or GitHub Secrets

### Dependency Management
- Automated dependency updates via Dependabot (weekly with grouped updates)
- Dependency version pinning via `uv.lock` with minimum version constraints in `pyproject.toml`
- Regular `uv sync` ensures reproducible builds
- Dependency vulnerability auditing via `pip-audit` in CI pipeline

### Infrastructure
- Non-root user (`appuser:appuser`, UID 1000) in Docker containers
- Multi-stage Docker builds with minimal `python:3.14-slim` base image
- Regular security updates for base images
- Input validation on all user-facing endpoints

## OWASP Top 10 Compliance

This project addresses the OWASP Top 10 (2021) as follows:

1. **Broken Access Control** - Repository allowlist enforces scope; least-privilege CI tokens per workflow
2. **Cryptographic Failures** - No custom crypto implementations; secrets handled exclusively via environment variables and GitHub Secrets
3. **Injection** - No SQL/command injection vectors; all GitHub API calls use parameterized PyGithub client; input validation on user-facing endpoints
4. **Insecure Design** - Security scanner agent proactively detects exposures; multi-layered defense (gitleaks + ruff + CodeQL + pip-audit)
5. **Security Misconfiguration** - Hardened Dockerfile with non-root user; gitleaks and CodeQL configurations maintained; comprehensive .gitignore
6. **Vulnerable and Outdated Components** - Dependabot tracks dependency health weekly; `pip-audit` runs in CI for real-time vulnerability detection; lockfile verification ensures integrity
7. **Identification and Authentication Failures** - GitHub PAT-based authentication; all tokens loaded from environment (never hardcoded)
8. **Software and Data Integrity Failures** - Supply-chain attacks mitigated via pinned dependencies in `uv.lock`; lockfile freshness verified in CI
9. **Security Logging and Monitoring** - All agent actions logged; Telegram notifications for critical events; Gitleaks + CodeQL results monitored
10. **SSRF** - No server-side request forgery vectors in agent architecture; all external calls are to well-defined API endpoints (GitHub, Ollama, Gemini)

## Security.txt

See `security.txt` (if present) for contact information.

## Responsible Disclosure

We kindly ask that you:
- Give us reasonable time to fix the issue before public disclosure
- Make every effort to avoid privacy violations, data destruction, and service interruption
- Provide clear and concise reproduction steps
