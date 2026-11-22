# Contributing to Github Assistance

Welcome! This project uses a fleet of AI agents to automate repository maintenance, security, and development.

## Getting Started

### Prerequisites
- [Bun](https://bun.sh) 1.4+
- GitHub Token with repo scope
- Telegram Bot Token (optional, for notifications)

### Environment Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   cd ts && bun install
   ```
3. Copy `.env.example` to `.env` and fill in your keys.

## Developing Agents

All agents should reside in `ts/src/agents/`. Each agent must:
- Inherit from `BaseAgent`.
- Adhere to the **150-line limit** per file.
- Have an `instructions.md` and any necessary `task-instructions*.md` templates.
- Ship tests (`ts/tests/`).

### Type Checking
```bash
cd ts && bun run typecheck   # tsc --noEmit, strict
```

### Testing
```bash
cd ts && bun test
```

## CI/CD Pipeline

`.github/workflows/validate.yml` runs the shared base-actions validation, a committed-secrets check, typecheck, tests and the no-cron guard. `security.yml` runs Gitleaks; `deploy.yml` builds and pushes the Docker image.

## Antigravity Protocol
Follow the rules defined in `AGENTS.md` strictly. Modularity, clean logic, and security are non-negotiable.
