# AGENTS.md

GitHub Assistance: a fleet of AI agents (Bun + TypeScript) that keeps a GitHub portfolio on autopilot. It handles PR review and merge, CI health, dependencies, repo standards, branch cleanup and secret scanning. Runs in Kubernetes. Agent output (PRs, issues, Telegram) is in pt-BR.

## Required: origin block in agent-created PRs and issues
Every PR or issue an agent creates MUST include this block in its body. This is non-negotiable, and it also applies to automatic comments on PRs and issues:
```
---
🤖 **Origem Automatizada**
- **Agente:** `<nome-do-agente>`
- **Modelo:** `<modelo-de-ia-utilizado>`
- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)
```
It applies to PRs opened by `OpencodeRunner.openPullRequest` (`ts/src/agents/opencode/runner.ts`) and `BaseAgent.openPullRequest` (`ts/src/agents/base-agent.ts`), and to issues created by any agent. Agents that open PRs: `builder` (always draft + `keep-draft`), `repo-standards`, `dependency-manager`, `secret-guard` (false-positive allowlist), `project-creator`. `pr-assistant` only commits to existing PRs.

## Stack
- Bun >= 1.2 and TypeScript, in `ts/`. Typecheck with `tsc --noEmit`, tests with `bun test`
- Durable job queue in SQLite (single writer), Telegram notifications
- AI through opencode (free models, fallback `litellm/cloud/auto`) and LiteLLM; tokenix as the code index (MCP); Gitleaks for secret scanning
- Docker image: Bun + Node + opencode + gitleaks, non-root user, `tini`

## Commands
Run from `ts/`:
- Install: `bun install --frozen-lockfile`
- Test: `bun test`
- Typecheck: `bun run typecheck`
- One agent: `bun src/cli/run-agent.ts <agent-name> [--pr owner/repo#N] [--ai-provider P] [--ai-model M]`
- All enabled agents, in dependency order: `bun src/cli/run-agent.ts all`
- Webhook server: `bun run webhook-server`. Queue CLI: `bun run queue`. PR insight: `bun run pr-insight`

Run from the repo root (also a CI step):
- Policy check, no cron in workflows: `bun ts/scripts/check-no-cron.ts --repo-dir .`

## Structure
- `ts/src/agents/<agent>/`: one folder per agent, with `agent.ts`, `instructions.md` (`## Persona`, `## Mission`) and its own modules
- `ts/src/agents/catalog.ts`: single source of truth (`AGENT_CATALOG`, `AGENT_ALIASES`). Registry, batch runner, orchestrator, health checks, entry points and dashboard derive from it
- `ts/src/agents/`: `base-agent.ts`, `batch-runner.ts`, `fleet.ts`, `orchestration.ts`, `registry.ts`, `agent-types.ts`
- `ts/src/agents/core/`: composite agents, agent contract, PR options, repo manager, reporting, metrics, utils
- `ts/src/agents/opencode/`: opencode integration (`models`, `local`, `runner`, `trace`)
- `ts/src/agents/pr_assistant/`: merge policy and flow, pipeline, billing gate, AGENTS.md gate, owner commands
- `ts/src/queue/`: durable SQLite queue (`schema`, `store`, `worker`, `outcome`, `read`, `overview`)
- `ts/src/webhooks/`: HTTP server (webhooks, `/api/*`, dashboard), auth, dispatcher
- `ts/src/config/`, `ts/src/insight/`, `ts/src/notifications/`, `ts/src/ai/`, `ts/src/utils/`, `ts/src/cli/`
- `ts/static/`: dashboard as plain HTML, CSS and ES modules, no build; served at `/dashboard/`
- `ts/scripts/`: benchmarks, policy checks, dry-runs. `ts/tests/`: `bun test` suites
- `config/`: `repositories.json` (allowlist of repos agents may change), `autonomy.json` (per-repo autonomy)

## Agents
Priority: Critical (security) > High (PR/CI) > Medium > Low. Each agent has a `*_ENABLED` toggle (see `.env.example`). Composite agents run older agents as stages (`stages` in the catalog). A stage toggle skips only that stage.

| Agent | Scope | Autonomy |
|---|---|---|
| `secret-guard` | Gitleaks across the portfolio (read-only), AI classification; a false positive becomes an allowlist PR; a real secret leaves history only with owner approval | suggest |
| `pr-assistant` | Owns every PR: AGENTS.md gate, diff-only review, SAST, inline conflicts, checks (local checks in repos without Actions), squash merge through `MergePolicy` | merge |
| `flow-watch` | Reports failing pipelines and stalled PRs on Telegram. Opens no PR, task or comment | observe |
| `dependency-manager` | CVEs first, then patch/minor; one grouped, tested PR | fix |
| `repo-standards` | `AGENTS.md` and `.agents/` in every active repo (no AGENTS.md first; `REPO_STANDARDS_MAX_PRS` per run; never two open PRs); README | fix |
| `branch-cleaner` | Deletes merged branches (never the default branch or one with an open PR) | fix |
| `builder` | Roadmap, code and UI through opencode. PRs are always **draft + `keep-draft`**; the bot reviews but never marks ready and never merges, even with `/merge` | fix, no merge |
| `project-creator` | Creates a new project anchored in the portfolio (opt-in, weekly) | suggest |

Old names still work from the CLI and run only their stage (`AGENT_ALIASES`). `code-reviewer` and `conflict-resolver` are now part of `pr-assistant` and do nothing, so an old CronJob does not run a second pass.

## Secret history rewrites need owner approval
- `secret-guard` opens a `secret-guard` issue with counts and rule names only. Files and lines go only to the private Telegram chat. It also sends an **Aprovar** button.
- Approval: the owner comments `/aprovar` on the issue, or taps the button in the private chat `TELEGRAM_CHAT_ID` (or an id in `TELEGRAM_APPROVER_IDS`)
- Approval runs `git-filter-repo --invert-paths` on the whole history and force-pushes branches and tags. This is irreversible. New findings need a new approval
- If the issue cannot be created (issues disabled), the button is resent on every run

## Common contract (every opencode run)
- Global `AGENTS.md` and the skills from juninmd/skills, at the latest commit. `core/agent-contract.ts` refreshes at most hourly (`AGENT_CONTRACT_REFRESH`). If the fetch fails, it keeps the copy in the image. The commit shows in PR bodies and review footers
- tokenix as the code index (MCP), latest build in the image with a checksum
- Free opencode models. On error, fall back to `litellm/cloud/auto`
- One identity: the GitHub App `juninmd-bot`

## Development rules
1. Size: max 150 lines per file (a target; several modules still exceed it, see `ROADMAP.md`)
2. Separation of concerns in every layer
3. Validation: every change passes `bun run typecheck` and `bun test`
4. Security: sensitive data stays out of AI context
5. Type safety: strong typing, avoid dynamic types
6. Testing: target 100% coverage. No coverage threshold is enforced in CI today
7. DRY, KISS and SOLID, applied with rigor
8. Merge method: **always squash**, to keep history clean

Cycle: Plan -> Act (or delegate to opencode) -> Validate -> Communicate. Agents do not call each other directly; dependencies live in `ts/src/agents/orchestration.ts`. The queue guarantees one job per `(kind, key)`. Every run produces a `RunResult` (`ts/src/results.ts`). `run-agent all` exits non-zero if any agent fails. A PR blocked by pending CI or by observe mode is not a failure.

Quotas: the GitHub API budget is 5,000 requests/hour (tracked by `BaseAgent`). Telegram is rate-limited in the notifier.

## Production (Kubernetes)
- Periodic routines, including the daily project pipeline, run as CronJob/Job in the cluster. Never dispatch them through GitHub Actions. Do not use `gh workflow run` as a smoke test of agent routines
- No workflow in this repo may use `on: schedule` or `cron`. `ts/scripts/check-no-cron.ts` enforces it in CI
- Webhook server and queue worker: **one replica** (single SQLite writer)
- GitHub runners cannot reach the cluster-internal LiteLLM address. Outside the cluster, set `LITELLM_API_BASE` to the public ingress (with `/v1`) and `LITELLM_API_KEY` to a virtual key
- Default image command: `run-agent pr-assistant`

Pending homologation:
- [ ] Validate a real `POST /v1/chat/completions` with the LiteLLM virtual key
- [ ] Run the real CronJob/Job: repo creation and an opencode task
- [ ] Rotate or revoke the virtual key if it is no longer needed

## Merge gate and CI billing failures
- **AGENTS.md required:** a repo without `AGENTS.md` at the root never gets a bot merge (`agents_md_missing`; an API error gives `agents_md_check_failed`, which fails closed). This holds even for dependabot or an owner `/merge`. Implemented in `ts/src/agents/pr_assistant/agents-md-gate.ts`. `repo-standards` opens the PR that creates the file
- Billing failures ("recent account payments have failed", "spending limit needs to be increased") mean the job never ran, so the cause is the account, not the code. By owner decision they do not block merge: `checkPipelineStatus` (`pr_assistant/pipeline.ts`) counts them as passed and lists them in `billing_checks`. Any other real failure on the same SHA still blocks
- Autonomous merge needs `AUTOMATION_MODE=autonomous` **and** the repo policy `mode=merge, merge=true` in `config/autonomy.json`. Missing, pending or cancelled evidence never merges. The merge is pinned to `expectedSha` (`merge-policy.ts`)

## opencode (opt-in, default off)
- Conflict resolution: `CONFLICT_OPENCODE_ENABLED=true`
- Pipeline fix: `PIPELINE_FIX_ENABLED=true`
- `SIMULATION_MODE=true` logs every decision and writes nothing external

## Creating an agent
0. First check whether the work fits as a stage of an existing agent. One scope per agent
1. Create `ts/src/agents/<name>/agent.ts`, extending `BaseAgent` (or `CompositeAgent` for stages), implementing `persona`, `mission` and `run()`. Add a short `instructions.md` with `## Persona` and `## Mission`, and no generic rules: the skills and the global AGENTS.md already apply
2. Add ONE `AgentSpec` in `ts/src/agents/catalog.ts` (priority, toggle, AI/Telegram, dependencies)
3. If it has a toggle, add the variable to `.env.example`. `Settings.enabled` derives from the catalog, and `ts/tests/env-documented.test.ts` checks the docs
4. Write tests, and update this file and the README. `ts/tests/` (catalog) fails if a step is missing

Good practice: single responsibility; use the shared clients (GitHub, Telegram); log important actions; handle errors gracefully; respect rate limits; save results as JSON; notify relevant events on Telegram.

## Security
- Secrets only through environment variables. Never send sensitive data to AI models. Sanitize output before logging
- `config/repositories.json` limits where agents may change code. `security-scanner` and `readme-curator` scan the whole portfolio without it (the scanner is read-only)
- Sensitive git operations run locally, not through remote agents
- Only `OWNER`, `MEMBER` and `COLLABORATOR` comments reach the merge LLM reviewer (`merge-decision.ts`). An evaluator error or absence yields `wait`, never a merge
- `/api/*` requires `Authorization: Bearer $ADMIN_API_TOKEN`. Without it configured, the API returns 403
- The dashboard (`/dashboard/`) is a static shell with no data. CSP is `default-src 'none'`; no inline script or style, no external origin; text is set only through `textContent`; the token lives in the tab's `sessionStorage`. `DASHBOARD_ENABLED=false` removes the route

<!-- base-actions-main-policy -->
## GitHub Actions — padrão obrigatório (@main)

- Referencie as actions internas sempre pelo branch, nunca por SHA:
  - `uses: juninmd/base-actions/<action>@main`
  - `uses: juninmd/base-actions/.github/workflows/<arquivo>.yml@main`
- Não fixe `@<sha>` em `juninmd/base-actions`: a atualização é centralizada no
  `main` e passa a valer no próximo run.
- PRs cujos checks não iniciam por billing/spending limit são mesclados pelo bot central
  `juninmd/base-actions/.github/workflows/auto-merge-billing-blocked.yml`.
  Para impedir o merge automático de um PR, aplique a label `do-not-merge`.