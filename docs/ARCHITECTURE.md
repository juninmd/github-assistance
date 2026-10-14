# Architecture — Durable Automation Core

This document describes the durable queue, safe-merge policy, autonomy model,
orchestration and insight layers added to the PR automation product. It is the
source of truth for operation, commands and honest limitations.

## 1. Durable job queue (`src/queue/`)

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

## 2. Safe merge policy (`src/agents/pr_assistant/merge_policy.py`)

Centralized, non-bypassable decision logic. `MergePolicy.evaluate()` returns
`merge | wait | blocked` with explicit reasons.

- **Evidence**: a PR merges only when every check/status of the *current* head
  SHA is conclusively green. `failed`, `pending`, `unknown`, `cancelled` and
  **absent evidence** never equal success.
- **No name/billing exemptions**: sonar/codecov/snyk/codex/codeclimate/etc. are
  no longer auto-ignored; billing-phrased failures are treated as real failures.
- **No bypass**: `bypass_validations` is always `False` for autonomous merge.
- **SHA re-validation**: the agent updates the branch against base
  (`update_pr_branch`), re-fetches the PR, re-runs `check_pipeline_status` on
  the new SHA, and `merge_pr(expected_sha=...)` refuses to merge if the head
  moved since validation.
- Pipeline status lives in `src/agents/pr_assistant/pipeline.py`; log
  collection for the AI fixer moved to `src/agents/pr_assistant/logs.py`.

## 3. Autonomy model (`src/config/autonomy_policy.py`)

Per-repository policy (`config/autonomy.json`): `mode` in
`observe | suggest | fix | merge`, `max_attempts`, `require_evidence`,
`required_checks`, `allowed_paths`, `merge`. Unknown repos default to
`observe`. Autonomous merge requires both `AUTOMATION_MODE=autonomous` and
repo policy `mode=merge, merge=true`.

**Evaluator**: `evaluate_comments_with_llm` (structured) never approves by
default. Evaluator unavailability or an invalid/empty response → `wait`
(reschedule). An explicit LLM `REJECT` → `blocked` with reason; the PR is **not
closed** automatically.

## 4. Orchestration (`src/agents/orchestration.py`, `batch_runner.py`)

- `validate()` rejects **missing** registered dependencies and **cycles**
  loudly; `get_execution_order`/`get_parallel_batches` raise instead of
  silently appending.
- A dependent whose dependency is outside the run is scheduled last and then
  **blocked by the runner** unless the dependency really succeeded
  (`batch_runner` tracks per-agent success).
- Durable exclusivity per `(repo, branch/PR)` is provided by the queue's unique
  `(kind, key)`; webhook/CLI/batch inputs all enqueue through the same store.

## 5. Results contract (`src/results.py`, `run_agent.py`)

`RunResult` (typed dataclass) records `task_id`, `repo`, `pr_ref`, `sha`,
`status`, item counts (from lists only — never dict keys), `duration_seconds`,
`api_calls`, `cost` (only when known — never invented), `attempts`,
`decision`, `next_action`, `evidence`. Batch runs propagate failures and
`run-agent all` exits non-zero when any agent failed; blocked PRs are reported
in `RunResult`/queue decisions but do not fail the run.

## 6. Insight / visibility (`src/insight/`, API, CLI)

- `GET /api/jobs` and `GET /api/prs/{owner}/{repo}/{number}/explain` on the
  webhook server; both require `Authorization: Bearer $ADMIN_API_TOKEN` and
  are disabled (403) when the token is unset.
- The merge comment gate only feeds comments from `OWNER`/`MEMBER`/`COLLABORATOR`
  to the LLM, so outsiders cannot inject a `MERGE` verdict.
- `queue-worker` CLI: `worker [--once|--observe]`, `reprocess --pr`,
  `list [--status]`, `stats`.
- `pr-insight` CLI: `explain --pr owner/repo#N`, `history --pr`.

## 7. Simulation mode

`SIMULATION_MODE=true` (or `--simulate` where supported) makes the PR Assistant
record every decision (`simulation` skip reason) without any external write:
no branch update, no merge, no comment, no Telegram, no conflict fix push.

## 8. Configuration reference

| Env | Default | Meaning |
|---|---|---|
| `WORKER_ENABLED` | `true` | run the durable worker thread in the webhook server |
| `QUEUE_POLL_INTERVAL_SECONDS` | `15` | worker poll interval |
| `QUEUE_LEASE_SECONDS` | `300` | job lease lifetime |
| `QUEUE_MAX_ATTEMPTS` | `3` | retries before `blocked` |
| `QUEUE_BACKOFF_SECONDS` | `60` | backoff multiplier |
| `MAX_CONCURRENT_WORKERS` | `1` | jobs per worker cycle (SQLite writer) |
| `SIMULATION_MODE` | `false` | dry-run all writes |
| `AUTONOMY_POLICY_PATH` | `config/autonomy.json` | per-repo autonomy |
| `PRIORITIES_PATH` | `config/priorities.json` | job prioritization |