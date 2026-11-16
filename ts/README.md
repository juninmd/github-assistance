# GitHub Assistance — Bun + TypeScript

Reescrita completa em `ts/`, **lado a lado** com o Python (`src/`, intocado). O Python só sai após o ok do dono (troca final de Dockerfile/CI).
Ferramentas externas (opencode, tokenix, gitleaks, semgrep…) **não foram alteradas**: são só invocadas como binários.

```bash
cd ts && bun install
bun test                              # 200+ testes (bun:test)
bun run typecheck                     # tsc --noEmit, strict
bun src/webhooks/server.ts            # webhooks + API admin + dashboard (:8080)
bun src/cli/queue.ts worker --once    # worker da fila
bun src/cli/run-agent.ts <agente>     # qualquer um dos 17 agentes
bun src/cli/insight.ts <owner/repo#n> # insight/explicação de um PR
bun scripts/<script>.ts               # benchmark, review-dry-run, readme-score, check-no-cron, …
```

## Paridade

| Área | Bun/TS |
|---|---|
| Config (features.toml, settings, allowlist, autonomy, priorities), catálogo, fleet | ✅ |
| Fila durável (`bun:sqlite`, WAL, leases, retries) | ✅ |
| Webhooks, API admin, retenção, throttle, GitHub App (JWT RS256), dashboard | ✅ (`Bun.serve`, sem FastAPI/PyJWT) |
| Cliente GitHub (REST cru), rate limiter, Telegram, IA/usage, opencode + tokenix | ✅ |
| **17/17 agentes** (PR assistant, conflict resolver, reviewer, scanner, secret remover, …) | ✅ |
| Insight/CLI, 8 scripts, guarda de env documentadas | ✅ |
| `Dockerfile.bun` + `.github/workflows/validate-ts.yml` | ✅ escritos, **não executados** (sem Docker/Actions aqui) |

## Melhorias na reescrita
- Pipeline de review com clone real: patch → revisão independente do fix → push só se aprovado.
- Corrigido bug do Python: `git push -c http…extraheader` (o `-c` tem de vir **antes** do subcomando); em `review_git.py` o push de fix falhava.
- Workers com pool (5) e `Semaphore` para o slot do opencode; orçamento de reviews por rodada.
- TypeScript estrito, zero dependências de runtime (fetch/sqlite/serve nativos do Bun).
- Teste que garante que toda variável de ambiente usada está documentada em `.env.example`.

## Cobertura de testes (honesto)
~200 testes TS vs ~1260 no Python. Cobertos: núcleo, fila, webhooks, todo o PR assistant (políticas, veredito, gate, e2e com git real), conflict resolver, insight. **Ainda não portados:** clientes (github/ai/jules/opencode) em detalhe, maioria dos testes específicos dos demais agentes, CLI da fila, API admin em profundidade.

Node permanece na imagem: `build_check` e `conflict_resolver` rodam `npm` nos clones.
