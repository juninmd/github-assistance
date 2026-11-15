# GitHub Assistance — port para Bun + TypeScript (em andamento)

Reescrita em `ts/`, **lado a lado** com o Python (`src/`). O Python só sai quando a paridade estiver provada.

```bash
cd ts && bun install
bun test            # testes portados (bun:test)
bun run typecheck
bun src/webhooks/server.ts          # webhooks + API admin + dashboard (:8080)
bun src/cli/queue.ts worker --once  # worker da fila
bun src/cli/run-agent.ts <agente>   # só agentes já portados
```

## Quadro de paridade

| Área | Python | Bun/TS | Testes portados |
|---|---|---|---|
| Config: features.toml, settings, allowlist, autonomy, priorities | ✅ | ✅ | ✅ |
| Catálogo de agentes + fleet | ✅ | ✅ | ✅ |
| Fila durável (SQLite WAL, leases, retries, overview) | ✅ | ✅ (`bun:sqlite`) | ✅ |
| Webhooks, API admin, retenção, throttle, App auth (JWT RS256) | ✅ | ✅ (`Bun.serve`, sem FastAPI/PyJWT) | ✅ |
| Dashboard (estático, CSP estrita) | ✅ | ✅ (mesmos arquivos) | ✅ |
| `run-agent`, health checks, RunResult | ✅ | ✅ | ✅ |
| Cliente GitHub, rate limiter, Telegram, IA/usage, opencode+tokenix | ✅ | ⏳ | ⏳ |
| 17 agentes (PR assistant, reviewer, scanner, …) | ✅ | ⏳ (registro lança "não portado") | ⏳ |
| Docker/CI trocados para Bun | — | ⏳ (só no corte final) | — |

Node continua na imagem final: `build_check` e `conflict_resolver` rodam `npm` nos clones.
