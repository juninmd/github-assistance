# Benchmark — durable queue, webhook API and cold start

Reproducible with `scripts/benchmark.py`, which only touches stable public entry
points so it also runs on older commits:

```bash
git worktree add ../base <base-sha> && cp scripts/benchmark.py ../base/scripts/
(cd ../base && uv run python scripts/benchmark.py --out /tmp/base.json)
uv run python scripts/benchmark.py --out /tmp/head.json
uv run python scripts/benchmark.py --compare /tmp/base.json /tmp/head.json
```

## Results (base `3d1d99d` → this change)

Median of 60–300 runs per scenario; queue seeded with 20,000 jobs; cold imports
are fresh interpreters (median of 7). Python 3.12, SQLite 3.45, 4 vCPU Xeon
2.3 GHz container. Absolute numbers vary per machine — compare the ratios.

| Scenario | Before (ms) | After (ms) | Speedup |
|---|---:|---:|---:|
| enqueue (new job) | 0.426 | 0.177 | 2.40x |
| enqueue (coalesce existing) | 0.318 | 0.131 | 2.43x |
| list_jobs (latest 100) | 28.409 | 0.607 | 46.81x |
| list_jobs (status=blocked, 100) | 6.710 | 0.611 | 10.98x |
| stats (count by status) | 1.113 | 0.893 | 1.25x |
| job_history (one PR) | 8.491 | 0.041 | 207.09x |
| claim + complete (1 job) | 2.532 | 0.363 | 6.97x |
| worker drain (500 jobs) | 552.370 | 188.540 | 2.93x |
| POST /webhooks/github | 3.268 | 2.213 | 1.48x |
| GET /api/jobs?limit=100 | 3.638 | 3.717 | 0.98x |
| cold import src.run_agent | 205.880 | 221.720 | 0.93x |
| cold import src.agents.pr_assistant.agent | 4031.923 | 223.739 | 18.02x |
| cold import src.insight.cli | 3846.257 | 239.630 | 16.05x |
| cold import src.queue.cli | 232.805 | 224.790 | 1.04x |
| cold import src.webhooks.server | 484.915 | 478.505 | 1.01x |

## What changed, and why it is faster

| Change | Effect |
|---|---|
| `litellm`, `google-genai` and `ollama` are imported on first use (`src/utils/lazy_import.py`) | `pr-assistant` and `pr-insight` no longer pay ~3.8 s of SDK imports on every CronJob start, even with AI disabled |
| Thread-local cached SQLite connection (`src/queue/schema.py::connection`) | no connect + schema parse per queue operation |
| `claim` and `complete` use one `UPDATE … RETURNING` | 1 statement instead of `SELECT` + N×(`UPDATE` + `SELECT`) |
| Indexes `idx_jobs_claim`, `idx_jobs_created`, `idx_jobs_status_created`, `idx_jobs_updated` | listing no longer scans and sorts the whole table; claim reads due jobs in order |
| Dropped `idx_jobs_kind_key` (duplicate of `UNIQUE(kind, key)`) and `idx_jobs_status` | one index less to maintain on every write |
| `job_history` filters by key in SQL | index lookup; also fixes a bug where a PR older than the newest 50 jobs had no history |

Not faster, by design: `GET /api/jobs` is dominated by JSON serialization of 100
rows, and the remaining cold-start cost is PyGithub/FastAPI themselves.
Durability is unchanged — WAL with `synchronous=FULL`, `BEGIN IMMEDIATE` writes.
