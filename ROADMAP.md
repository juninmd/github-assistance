# 🗺️ ROADMAP.md - Github Assistance Evolution

## 🏁 Phase 1: Core Foundation ✅
- [x] Initial scaffolding and repository setup.
- [x] Basic architecture and structural implementation.
- [x] Antigravity documentation alignment.

## 🚧 Phase 2: Refinement & Depth ✅
- [x] Agent implementations (16 agents dispatched via `run-agent`).
- [x] Test suite above the 80% coverage gate (~970 tests, ~84% coverage).
- [x] Durable queue, non-bypassable safe-merge policy, and insight layer.

## 🚀 Phase 3: Polish & Scale (Current)
- [ ] **Modularity**: bring the largest modules under the 150-line guideline
      (`pr_assistant/agent.py`, `pr_assistant/conflict_resolver.py`,
      `jules/client.py`, and ~20 others still exceed it).
- [ ] **Coverage**: raise the lowest modules (`secret_remover/utils.py`,
      `insight/cli.py`, `queue/cli.py`, `utils/proc.py`, `utils/retry.py`).
- [ ] **Configuration**: keep every documented `.env.example` value wired to
      `src/config/settings.py` (regression test now guards the agent toggles).
- [ ] **Release automation**: fully automated Docker image publish pipeline.

## 🎯 v1.0 Milestone
A robust, stable, and Antigravity-compliant project ready for scale.
