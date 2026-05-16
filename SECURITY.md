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
- **Gitleaks**: Automated scanning of all repositories every 2 days for leaked credentials
- **Secret Remover Agent**: AI-powered identification and remediation of real secrets
- **All findings are sanitized**: Actual secret values are never exposed in reports

### CI/CD Security
- **Least-privilege permissions**: Each workflow uses minimal GitHub token scopes
- **SAST scanning**: Static analysis via ruff with security-focused rule sets
- **Automated dependency updates**: Dependabot configured for pip, Docker, and GitHub Actions
- **No secrets in code**: All sensitive values via environment variables or GitHub Secrets

### Dependency Management
- Automated dependency updates via Dependabot (weekly)
- Dependency version pinning via `uv.lock`
- Regular `uv sync` ensures reproducible builds

### Infrastructure
- Non-root user in Docker containers
- Regular security updates for base images
- Input validation on all user-facing endpoints

## OWASP Top 10 Compliance

This project addresses the OWASP Top 10 (2021) as follows:

1. **Broken Access Control** - Repository allowlist enforces scope; least-privilege CI tokens
2. **Cryptographic Failures** - No custom crypto; secrets handled via environment variables
3. **Injection** - No SQL/command injection vectors; parameterized GitHub API calls
4. **Insecure Design** - Security scanner agent proactively detects exposures
5. **Security Misconfiguration** - Hardened Dockerfile; gitleaks configuration maintained
6. **Vulnerable and Outdated Components** - Dependabot tracks dependency health
7. **Identification and Authentication Failures** - GitHub PAT-based authentication
8. **Software and Data Integrity Failures** - Supply-chain attacks mitigated via pinned dependencies
9. **Security Logging and Monitoring** - All agent actions logged; Telegram notifications
10. **SSRF** - No server-side request forgery vectors in agent architecture

## Security.txt

See `security.txt` (if present) for contact information.

## Responsible Disclosure

We kindly ask that you:
- Give us reasonable time to fix the issue before public disclosure
- Make every effort to avoid privacy violations, data destruction, and service interruption
- Provide clear and concise reproduction steps
