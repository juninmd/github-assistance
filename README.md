# Github Assistance

[![CI/CD Pipeline](https://github.com/juninmd/github-assistance/actions/workflows/ci.yml/badge.svg)](https://github.com/juninmd/github-assistance/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/juninmd/github-assistance/branch/main/graph/badge.svg)](https://codecov.io/gh/juninmd/github-assistance)
[![Dependabot](https://img.shields.io/badge/dependabot-active-brightgreen.svg)](https://github.com/juninmd/github-assistance/security/dependabot)
[![Gitleaks](https://img.shields.io/badge/secret_scanning-gitleaks-blue.svg)](https://github.com/juninmd/github-assistance/actions/workflows/gitleaks-scan.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/linter-ruff-purple.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/type_checker-pyright-yellow.svg)](https://github.com/microsoft/pyright)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()
[![Protocol: Antigravity](https://img.shields.io/badge/Protocol-Antigravity-orange.svg)]()

> A modern, high-performance project built with **Python 3.12+**. Orchestrated under the Antigravity protocol.

## Features

- **High Performance**: Optimized for speed and low resource usage.
- **Clean Architecture**: Built following strict Antigravity guidelines.
- **Automated CI/CD**: Multi-stage pipeline with linting, type checking, testing, security scanning, and deployment.

## CI/CD Pipeline

The project uses a comprehensive CI/CD pipeline via GitHub Actions:

| Stage | Tools | Description |
|---|---|---|
| Lint | Ruff | Code formatting and linting |
| Type Check | Pyright | Static type checking |
| Security | Bandit, pip-audit, Gitleaks | SAST and dependency vulnerability scanning |
| Test | Pytest, pytest-cov | Unit/integration tests with coverage reporting |
| Build | Hatchling, uv | Package building and artifact generation |
| Deploy | Docker | Container image build and push |

## Quality Gates

- **Linting**: Ruff with pycodestyle, pyflakes, isort, pyupgrade, and bandit-security rules
- **Type Safety**: Pyright in basic mode with strict import checking
- **Security**: Bandit SAST scanning + pip-audit dependency auditing + Gitleaks secret scanning
- **Coverage**: Test coverage reported to Codecov (80%+ target)
- **Dependencies**: Dependabot for automated weekly updates with grouped PRs

## Tech Stack

- **Primary Technology**: Python 3.12+
- **Architecture**: Modular and domain-driven.
- **Package Manager**: uv (fast Python package installer)

## Antigravity Protocol

This project follows the **Antigravity** code standards:
- **150-Line Limit**: Applied to all logic modules.
- **Strict Typing**: Avoiding dynamic/any types.
- **Clean Code**: DRY, KISS, and SOLID principles applied rigorously.

---

*"Simplicity is the ultimate sophistication."*
