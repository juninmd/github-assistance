# Architecture — Durable Automation Core

This document describes the durable queue, safe-merge policy, autonomy model,
orchestration and insight layers added to the PR automation product. It is the
source of truth for operation, commands and honest limitations.

## 1. Durable job queue (`ts/src/queue/`)

Webhook deliveries and their PR jobs are persisted **atomically** in SQLite
(`data/webhooks.db`, WAL mode). A background `QueueWorker` claims due jobs.

- **States**: `pending → running → succeeded | failed | blocked`.
- **Lease**: a claimed job holds an expiring lease; after a crash/restart the
  stale lease is recovered to `pending` and reprocessed exactly once.
- **Idempotency**: one row per `(kind, key)`; re-deliveries coalesce instead of
  duplicating. Effects (merge, comments) are idempotent on GitHub.
- **Retries**: `failed` jobs retry with bounded `max_attempts` and exponential
  backoff, then become `blocked`.
- **Re-evaluation guarantee**: a new event for a running job sets
  `reprocess_pending`; when the current round finishes a fresh round is
  scheduled immediately, so no event is lost.
- **Storage**: one cached connection per thread (`schema.connection`), claim and
  completion as single `UPDATE … RETURNING` statements, and indexes for the
  claim and listing paths. Numbers: [BENCHMARK.md](BENCHMARK.md).
- **Mode**: `AUTOMATION_MODE=observe` persists and records jobs with no external
  effects; `autonomous` runs the PR Assistant for the specific PR.

### SQLite limits (documented)

- Single-writer per file; concurrency is bounded by `MAX_CONCURRENT_WORKERS`
  (default `1`). For N replicas sharing one volume, only one writer is safe.
- Do not run multiple webhook/worker replicas against the same DB file unless
  the file lives on a volume with real file locking; the queue is designed for
  **one replica**. Multi-replica support requires a shared queue (e.g. Redis).
- Cluster hom**o**logation is Kubernetes-only (CronJob/Job); never via
  `gh workflow run`.

## 2. Safe merge policy (`ts/src/agents/pr_assistant/merge_policy.ts`)

Centralized, non-bypassable decision logic. `MergePolicy.evaluate()` returns
`merge | wait | blocked` with explicit reasons.

- **Evidence**: a PR merges only when every check/status of the *current* head
  SHA is conclusively green. `failed`, `pending`, `unknown`, `cancelled` and
  **absent evidence** never equal success.
- **No name exemptions**: sonar/codecov/snyk/codex/codeclimate/etc. are not
  auto-ignored. The only exception is GitHub Actions *billing refusals* (job
  never started): by owner decision they count as passed and are listed in
  `billing_checks`; any other failure on the SHA still blocks.
- **No bypass**: `bypass_validations` is always `False` for autonomous merge.
- **SHA re-validation**: the agent updates the branch against base
  (`update_pr_branch`), re-fetches the PR, re-runs `check_pipeline_status` on
  the new SHA, and `merge_pr(expected_sha=...)` refuses to merge if the head
  moved since validation.
- Pipeline status lives in `ts/src/agents/pr_assistant/pipeline.ts`; log
  collection for the AI fixer moved to `ts/src/agents/pr_assistant/pipeline-logs.ts`.

## 3. Autonomy model (`ts/src/config/autonomy.ts`)

Per-repository policy (`config/autonomy.json`): `mode` in
`observe | suggest | fix | merge`, `max_attempts`, `require_evidence`,
`required_checks`, `allowed_paths`, `merge`. Unknown repos default to
`observe`. Autonomous merge requires both `AUTOMATION_MODE=autonomous` and
repo policy `mode=merge, merge=true`.

**Evaluator**: `evaluate_comments_with_llm` (structured) never approves by
default. Evaluator unavailability or an invalid/empty response → `wait`
(reschedule). An explicit LLM `REJECT` → `blocked` with reason; the PR is **not
closed** automatically.

## 4. Orchestration (`ts/src/agents/core/orchestration.ts`, `batch_runner.ts`)

- Priorities, dependencies, toggles and capabilities come from the agent
  catalog (`ts/src/agents/catalog.ts`), the single source of truth.

- `validate()` rejects **missing** registered dependencies and **cycles**
  loudly; `get_execution_order`/`get_parallel_batches` raise instead of
  silently appending.
- A dependent whose dependency is outside the run is scheduled last and then
  **blocked by the runner** unless the dependency really succeeded
  (`batch_runner` tracks per-agent success).
- Durable exclusivity per `(repo, branch/PR)` is provided by the queue's unique
  `(kind, key)`; webhook/CLI/batch inputs all enqueue through the same store.

## 5. Results contract (`ts/src/results.ts`, `cli/run-agent.ts`)

`RunResult` (typed dataclass) records `task_id`, `repo`, `pr_ref`, `sha`,
`status`, item counts (from lists only — never dict keys), `duration_seconds`,
`api_calls`, `cost` (only when known — never invented), `attempts`,
`decision`, `next_action`, `evidence`. Batch runs propagate failures and
`run-agent all` exits non-zero when any agent failed; blocked PRs are reported
in `RunResult`/queue decisions but do not fail the run.

## 6. Insight / visibility (`ts/src/insight/`, `ts/src/webhooks/admin_api.ts`, `ts/src/dashboard/`)

- Admin API, all behind `Authorization: Bearer $ADMIN_API_TOKEN` (403 when unset):
  `GET /api/jobs` (`status`, `repo`, `q`, `limit`, `offset` → `{jobs, total}`),
  `GET /api/jobs/{id}`, `POST /api/jobs/{id}/reprocess` (409 while running),
  `GET /api/overview?hours=1..168` (totals, backlog, outcome buckets, decisions,
  top repositories, webhook events, service state), `GET /api/agents` (catalog +
  whether each agent can run with the current settings) and
  `GET /api/prs/{owner}/{repo}/{number}/explain`.
- Dashboard at `/dashboard/` (`DASHBOARD_ENABLED`, default on): a static shell
  with no data of its own. No build step, no third-party origin, CSP
  `default-src 'none'` with only `'self'` scripts/styles, `no-cache` + ETag.
  The token is kept in `sessionStorage` (per tab). Charts are HTML boxes and
  inline SVG, text is inserted with `textContent` only.
- Aggregations live in `ts/src/queue/overview.ts` (SQL over a bounded window).
  The queue keeps one row per `(kind, key)`, so the charts show each PR's
  *latest* outcome bucketed by its last update, not a full event history.
- The merge comment gate only feeds comments from `OWNER`/`MEMBER`/`COLLABORATOR`
  to the LLM, so outsiders cannot inject a `MERGE` verdict.
- `queue-worker` CLI: `worker [--once|--observe]`, `reprocess --pr`,
  `list [--status]`, `stats`.
- `pr-insight` CLI: `explain --pr owner/repo#N`, `history --pr`.

## 7. Simulation mode

`SIMULATION_MODE=true` (or `--simulate` where supported) makes the PR Assistant
record every decision (`simulation` skip reason) without any external write:
no branch update, no merge, no comment, no Telegram, no conflict fix push.

## 7.1 PR review pipeline (`ts/src/agents/pr_assistant/review-*.ts`)

A model's claim never blocks or approves a PR on its own word. Each review runs:

1. **Scope** (`review-workspace.ts`, `review-refine.ts`): the clone pins
   `origin/<base>` to the PR's merge-base and keeps only the files GitHub lists
   for the PR, so a PR that is behind its base is not blamed for the base's
   newer commits.
2. **Triage** (`review-triage.ts`): lockfiles, generated code, binaries and
   deleted files are never sent to the model; the rest is ordered by risk
   (runtime/CI code, config, tests, docs) and packed into packages. A file
   bigger than a package is split with correct line numbers, not truncated.
3. **Find** (`review-flow.ts`): one model call per package (up to
   `REVIEW_MAX_PACKAGES`). Every finding must quote a line of code as
   `evidence`.
4. **Ground** (`review-grounding.ts`, deterministic): a finding whose quoted
   code is not in the diff or the repo, or whose file is not in the PR, is
   dropped. The line number comes from where the quote was found. An `error`
   with no quote is capped at `warn`.
5. **Verify** (`review-verify.ts`, `REVIEW_VERIFY_ENABLED`): a second,
   sceptical pass sees each `warn`/`error` next to the real code and may
   refute or downgrade it, never raise it. If the verifier is unavailable,
   nothing changes.
6. **Decide** (`review-verdict.ts::decide`): a surviving `error` always means
   `REQUEST_CHANGES`, even if the model said `APPROVE`; a `REQUEST_CHANGES`
   whose blocking claims were all discarded becomes `APPROVE`; otherwise the
   model's verdict stands. Auto-fix only acts on findings that survived.

## 7.1.1 Merge gate (`agent.ts`, `merge-flow.ts`)

Order per PR: skips (age, hold label from `merge-block.ts`: `do-not-merge`,
`wip`, `auto-merge-skip`, any case or separator; re-checked right before the
merge and not overridden by `/merge`; untrusted author by **exact** login,
owner `/hold`) → conflicts → red pipeline (fixed, not reviewed) → owner `/merge`
→ model review → pipeline pending → merge step.

- **Verdict identity** (`bot-identity.ts`): review comments count only from the
  App login read from `GET /app` at run start, `GITHUB_BOT_LOGIN` and legacy
  names. With App auth the owner's own comments never carry a verdict.
- **Approval pin** (`review-approval.ts`, `diff-fingerprint.ts`): the verdict
  matches the head SHA, or the fingerprint of the PR's own `+/-` lines, so a
  clean "update branch" keeps the approval while any change to the PR's lines
  needs a new review.
- **Owner commands** (`owner-commands.ts`): `/hold`/`/unhold`, `/review`
  (fresh verdict), `/merge` (explicit approval, valid only if newer than the
  newest commit; added lines are still scanned for credentials). A plain-words
  objection ("não mergeia", "do not merge", "wip") by the owner blocks.
- **Waiver tiers** (`review-waiver.ts`): no token/clone failure is an infra
  error, retried next run, never waived. A model outage first posts a pending
  notice; the merge goes on without model review only after
  `REVIEW_WAIVE_AFTER_MINUTES`, on diffs up to `REVIEW_WAIVE_MAX_LINES`, at most
  `REVIEW_WAIVE_MAX_PER_RUN` per run.
- **Dependency lane** (`dependency-lane.ts`): dependabot/renovate skip the model
  but only dependency files may change, added lines are scanned, and at least
  one real check (not advisory, not billing-refused) must pass, unless Actions
  are billing-blocked (then the billing path below applies).
- **No CI** (`local-checks.ts`): billing-blocked or CI-less PRs run the
  project's own build/test gate on a clone of the exact head before merging; a
  red result blocks, environment problems are reported as skipped. The billing
  credential scan covers every file (no cap); files without a patch are read
  from the head, and an unreadable text file blocks.

## 7.2 Merge conflict resolution (`ts/src/agents/pr_assistant/conflict-*.ts`)

The PR Assistant handles conflicts in its own cycle (`conflict-flow.ts`,
`PR_ASSISTANT_RESOLVE_CONFLICTS`); the Conflict Resolver agent uses the same
flow. Dependabot PRs get `@dependabot rebase` (at most every 6 h) instead of a
push. Every agent that pushes to a PR branch (autofix, pipeline fix, conflict
resolution) holds the `bot/busy` lease label first. The
`needs-manual-conflict-resolution` label is removed once the PR is mergeable.

1. **Merge with the ancestor visible.** The base is merged with
   `merge.conflictStyle=zdiff3` (`diff3` on older git), so each conflict block
   carries ours, the common ancestor and theirs.
2. **Classify before any model call** (`conflict-plan.ts`). The run stops with
   a specific reason when a file was deleted/renamed on one side, when a
   conflicted file has no text markers (binary or mode), when a lockfile has no
   regeneration command, or when the merge touches `.github/workflows` and the
   token is known to lack the `workflow` scope. Lockfiles with a command are
   regenerated from the merged manifest and never reach a model.
3. **Resolve block by block** (`conflict-hunks.ts`). Blocks where both sides
   ended up equal, or where only one side really changed the ancestor, are
   settled without a model. For the others the model receives the three
   versions, the file path, the PR title and read-only context, and returns
   only the lines that replace the block. Code outside a conflict is therefore
   never rewritten.
4. **Fail closed.** An empty answer, surviving markers, `CANNOT_RESOLVE` or an
   answer far bigger than both sides fails the file; the first file that fails
   stops the run and nothing is pushed.
5. **Validate, then push.** No leftover markers, lockfiles regenerated, project
   build/test gate (`build-check.ts`), then one merge commit.

## 8. Configuration reference

| Env | Default | Meaning |
|---|---|---|
| `WORKER_ENABLED` | `true` | run the durable worker thread in the webhook server |
| `QUEUE_POLL_INTERVAL_SECONDS` | `15` | worker poll interval |
| `QUEUE_LEASE_SECONDS` | `300` | job lease lifetime |
| `QUEUE_MAX_ATTEMPTS` | `3` | retries before `blocked` |
| `QUEUE_BACKOFF_SECONDS` | `60` | backoff multiplier |
| `MAX_CONCURRENT_WORKERS` | `1` | jobs per worker cycle (SQLite writer) |
| `WEBHOOK_PURGE_ENABLED` | `true` | purge old `deliveries` rows, then `VACUUM` |
| `WEBHOOK_RETENTION_DAYS` | `3` | delivery payloads older than this are deleted (also the redelivery-dedupe window) |
| `WEBHOOK_PURGE_INTERVAL_SECONDS` | `21600` | purge cadence; first run 30s after start |
| `DASHBOARD_ENABLED` | `true` | serve the control-room UI at `/dashboard/` |
| `SIMULATION_MODE` | `false` | dry-run all writes |
| `AUTONOMY_POLICY_PATH` | `config/autonomy.json` | per-repo autonomy |
| `PRIORITIES_PATH` | `config/priorities.json` | job prioritization |
## Configuration layers

Precedence: environment (and `.env`) > `config/features.toml` (`[env]` table, override
path with `FEATURES_FILE`) > code defaults. The file is for non-secret toggles and tuning
(see `config/features.toml.example`); secret-looking keys (TOKEN/KEY/SECRET/PASSWORD)
are ignored there. `AI_TOKEN_BUDGET` caps estimated LLM tokens per run.
