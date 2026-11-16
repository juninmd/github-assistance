# Task: Security Hardening for {{repository}}

## Identified Issues
{{issues}}

## Security Checklist

### 1. Secrets Management
- [ ] Ensure .gitignore includes:
  ```
  # Environment and secrets
  .env
  .env.local
  .env.*.local
  *.key
  *.pem
  *.p12
  secrets/
  config/secrets.yml
  ```
- [ ] Scan for accidentally committed secrets (use git-secrets or truffleHog)
- [ ] Use environment variables for all sensitive data

### 2. Dependency Security
- [ ] Run `npm audit` or `pip-audit` and fix vulnerabilities
- [ ] Pin dependency versions in production

### 3. Code Security
- [ ] Implement input validation for all user inputs
- [ ] Use parameterized queries (prevent SQL injection)
- [ ] Implement rate limiting on APIs
- [ ] Add CORS configuration
- [ ] Implement proper authentication/authorization

### 4. CI/CD Security
- [ ] Store secrets in GitHub Secrets, never in code
- [ ] Use least-privilege permissions for CI tokens
- [ ] Implement secret scanning in CI pipeline
- [ ] Add SAST (Static Application Security Testing) tools
- [ ] **NEVER create scheduled (cron) GitHub Actions** (`on: schedule:` / `- cron:`).
      They consume runner minutes continuously, even on idle repos. Prefer
      `workflow_dispatch` or event-driven triggers; centralize any periodic job.

### 5. Infrastructure Security
- [ ] Enable HTTPS everywhere
- [ ] Implement security headers (CSP, HSTS, etc.)
- [ ] Regular security updates and patches
- [ ] Proper error handling (don't leak sensitive info)

## OWASP Top 10 Compliance
Verify the application addresses:
1. Broken Access Control
2. Cryptographic Failures
3. Injection
4. Insecure Design
5. Security Misconfiguration
6. Vulnerable and Outdated Components
7. Identification and Authentication Failures
8. Software and Data Integrity Failures
9. Security Logging and Monitoring Failures
10. Server-Side Request Forgery (SSRF)

### 6. Security Testing (MANDATORY)
- [ ] **You MUST write corresponding unit or integration tests** for all newly added security fixes (e.g. input validation, sanitization filters, rate limiting, authentication helpers).
- [ ] Tests must cover standard valid inputs as well as malicious or invalid inputs (SQL injection payloads, XSS payloads, overly large payloads, unauthorized requests) to prove the security mechanism works.
- [ ] Do not complete the task or submit a PR without verified security tests.

## Deliverables
Create a PR with:
- Updated .gitignore
- Corresponding unit/integration tests for any added validation, controls, or security logic (testing normal and malicious input paths).
- Any additional security improvements
- Security audit report in PR description

## Forbidden Files (do NOT create or commit)
- `.github/dependabot.yml` (consumes GitHub Actions quota)
- `SECURITY.md`
- `SECURITY_AUDIT.md`
- Any other GitHub Actions workflow with `on: schedule:` / `- cron:`

Report findings only in the PR description, never as these files.

Follow the principle of least privilege throughout.
