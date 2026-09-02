# Manutenção Autônoma de Repositórios — Proposta de Arquitetura

Objetivo: manter todos os repositórios do portfólio atualizados (README, AGENTS.md,
stack, dependências, bugs) de forma autônoma, **sem quebrar o código atual**, usando as
skills de `juninmd/skills` e priorizando tokens gratuitos (OpenCode free models, Jules,
LiteLLM como fallback).

## 1. Diagnóstico

| Componente | Estado hoje | Problema |
| --- | --- | --- |
| **github-assistance** | 16 agentes Python, Jules client, OpenCode embarcado (`opencode_local.py`), `vibe_code_client.py` (não mais ligado ao `base_agent`), CronJobs no k8s | Cada agente decide sozinho o que fazer e executa na hora. Não há fila, prioridade entre repos, nem rastreio do que já foi aplicado. `senior_developer` cria tasks por *análise heurística* e pula direto para execução. |
| **vibe-code** | 156 arquivos TS no server, 15 engines, kanban com `priority` + `dependsOn` + `sweepBacklog`, worktrees, criação de PR, review de 5 personas, LiteLLM por virtual key, skills loader lendo `~/.agents` | Fez demais: sessions board, inbox, templates, prompts, agent-templates, 3 pacotes de DB, 18 tabelas vs 11 na migração, lixo na raiz (`fix_*.js`, `old_*.txt`, logs), dois lockfiles. A parte que importa (backlog → launch → PR) está enterrada. Não expõe **capacidade** nem **webhook** para quem enfileira. |
| **skills** | 80 skills com Preflight/Workflow/Stop/Checklist, validador e evals de roteamento | Só o vibe-code as monta (init container `skills-bootstrap`). github-assistance não as usa; Jules não as vê. |

Conclusão: não falta engine nem skill. Falta um **planejador determinístico** que transforme
"estado do repo" em tasks pequenas e ordenadas, e um **runtime de kanban enxuto** que as
execute com o provedor mais barato disponível e devolva um PR verificado.

## 2. Divisão de responsabilidades

```text
skills (fonte da verdade "como fazer")
   │  sincronizado para ~/.agents (vibe-code) e embutido no prompt (Jules)
   ▼
github-assistance = PLANNER + DISPATCHER + CLOSER   (Python, CronJob diário no k8s)
   detecta drift → gera Maintenance Plan → enfileira no kanban → acompanha PR → auto-merge por tier
   │  POST /api/tasks (idempotencyKey, dependsOn, priority, skills[], runtimeProfile)
   ▼
vibe-code = KANBAN RUNTIME                           (Bun/TS, sempre ligado)
   backlog → worktree → harness (opencode free | opencode via LiteLLM | claude | ...) → gates → PR
   │  webhook task.done / task.failed
   ▼
GitHub PR + CI verde → github-assistance fecha o ciclo (merge, issue de status, Telegram)
```

Jules continua sendo um *runtimeProfile* externo: o dispatcher cria sessão direto pela
API dele quando o tier pede raciocínio maior (migração de stack, bug com plano) e o
`jules_tracker` já cuida de aprovação de plano e perguntas.

## 3. O contrato de uma task de manutenção

Toda task nasce de um **detector** puro (sem LLM), carrega um `idempotencyKey`
(`<repo>:<tipo>:<hash do estado>`) e referencia skills pelo nome. Tiers definem o que
pode ser mesclado sem humano:

| Tier | Tipos | Skills | Gate para merge |
| --- | --- | --- | --- |
| **T0 Baseline** | CI ausente, sem lockfile, sem script de teste, sem `.agents` | `test-engineering`, `cloud-devops`, `project-structure` | CI verde; auto-merge |
| **T1 Docs** | README curto/stale, AGENTS.md ausente/divergente, CHANGELOG | `documentation`, `agents-md`, `docs-verification` | CI verde + review docs; auto-merge |
| **T2 Deps** | patch/minor desatualizadas, CVE (`pip-audit`, `bun audit`) | `dependency-upgrade` (nova), `finishing-dev` | CI verde + testes existentes; auto-merge patch/minor, major = 1 por PR e draft |
| **T3 Stack** | Node/JS → Bun + TS, CommonJS → ESM, pnpm → bun | `migration-engineering`, `backend-node`, `legacy-discovery` | Sempre em etapas com `dependsOn`; PR draft; humano aprova; review `STRICT` |
| **T4 Bugs** | issue `bug`, CI vermelho no main, `pr_assistant` falhas repetidas | `diagnostics`, `incident-response`, `test-engineering` | Teste de regressão obrigatório no diff; auto-merge só se cobrir a issue |

Regras que garantem "não quebrar":

1. **Baseline antes de tudo.** Se o repo não tem teste nem build no CI, a única task
   permitida é T0. Nada de T2/T3 em repo sem rede de proteção.
2. **Preflight = Postflight.** O prompt de cada task contém os comandos reais do repo
   (extraídos de `package.json`/`pyproject`/CI, nunca inventados — regra da skill
   `agents-md`) e exige que o agente rode antes e depois. Diff sem os checks = task falha.
3. **Um objetivo por PR.** Migrar stack vira uma cadeia: `add bun lockfile` → `scripts
   bun` → `tsconfig strict incremental` → `converter src/ por pasta` → `remover node
   runtime`. Cada elo depende do anterior via `dependsOn` e só entra na fila quando o
   PR anterior foi mesclado.
4. **Escada de modelo, não de tentativas.** 1ª tentativa: OpenCode free model. Falhou
   nos gates: OpenCode via LiteLLM (modelo barato). Falhou de novo: Jules ou Claude, só
   para T3/T4. Depois disso a task vai para `blocked` com o log; nunca loop infinito.
5. **Rollback = revert do PR.** Como tudo é PR pequeno com CI verde, desfazer é trivial.
   github-assistance reverte automaticamente se o main ficar vermelho até 2 h após o merge.

## 4. Estratégia de tokens gratuitos

| Provedor | Uso | Quota | Como entra |
| --- | --- | --- | --- |
| OpenCode free (`*-free`, `big-pickle`) | T0, T1, T2 patch/minor | ilimitado na prática | engine `opencode` do vibe-code com `litellm_enabled=false`; `get_random_free_opencode_model` já existe no GA |
| Jules | T3, T4, tasks com plano | 100 sessões/dia | `JulesClient.create_session` a partir do dispatcher; `jules_tracker` acompanha |
| LiteLLM | fallback pago controlado, reviewers | virtual key por run (já existe) | `runtimeProfile: opencode-litellm` |
| GitHub Actions | **não** executa agentes (policy `check_no_cron_workflows`) | — | só CI dos repos alvo |

O vibe-code precisa expor `GET /api/capacity` (slots livres por profile, quota Jules
restante informada pelo GA) para o dispatcher não enfileirar o que não vai rodar hoje —
é o "autopilot admission control" que já está no ROADMAP do vibe-code.

## 5. Plano de implementação (PRs pequenos, cada um útil sozinho)

### Fase 1 — github-assistance (1 semana)

- [ ] `config/maintenance.yaml`: por repo, `targetStack` (ex.: `bun-ts`), `autoMergeTiers`,
      `cadence`, `maxOpenPRs` (default 2). Repos fora do arquivo herdam o default.
- [ ] `src/agents/maintenance/detectors/*.py`: funções puras `detect_*(repo_snapshot) ->
      list[MaintenanceTask]` para T0–T4. Snapshot vem de uma única chamada de árvore +
      arquivos-chave; testável com fixtures, sem rede.
- [ ] `src/agents/maintenance/planner.py`: aplica tiers, baseline gate, `dependsOn` das
      cadeias, corta em `maxOpenPRs`, gera `idempotencyKey`.
- [ ] `src/agents/maintenance/dispatcher.py`: religa `VibeCodeClient` (hoje órfão) com
      os novos campos; fallback `opencode_local` se vibe-code indisponível; Jules para T3/T4.
- [ ] `src/agents/maintenance/closer.py`: consome webhook `task.done`, espera CI,
      auto-merge por tier (`squash`), reverte se main quebrar, atualiza a issue fixa
      `🛠️ Maintenance status` de cada repo e manda o digest no Telegram.
- [ ] Skills para o Jules: o dispatcher lê `~/.agents/skills/<name>/SKILL.md` (mesmo
      init container do vibe-code) e concatena ao prompt, respeitando o `## Stop`.
- [ ] Aposentar/absorver: `senior_developer.task_creator`, `readme_curator`,
      `intelligence_standardizer` viram detectores. Menos agentes, uma fila.

### Fase 2 — vibe-code vira "kanban runtime" (1–2 semanas)

- [ ] API: `POST /api/tasks` aceita `idempotencyKey` (retorna a task existente),
      `skills[]`, `runtimeProfile`, `gates` (`{preflight: [...], postflight: [...]}`);
      `GET /api/capacity`; `settings.webhookUrl` → `POST task.done|task.failed` assinado.
- [ ] Executor: se `gates.postflight` falhar, status `failed` com motivo, sem PR.
      Escada de modelo por `runtimeProfile` (aproveita "Intelligent Model Progression" do ROADMAP).
- [ ] Unificar `agents/queue.ts` com `sweepBacklog` (hoje duplicados).
- [ ] Cortar superfície: apagar lixo da raiz, `homologacao/`, `pnpm-lock.yaml`; colocar
      `sessions`, `inbox`, `prompts`, `templates`, `agent-templates` atrás de
      `VIBE_CODE_EXPERIMENTAL=true` ou remover; alinhar `db/schema.ts` com as migrações.
- [ ] Manter: board, TaskDetail com logs, review pipeline, skills loader, LiteLLM keys.

### Fase 3 — skills (paralelo)

- [ ] Novas skills: `dependency-upgrade`, `node-to-bun-migration`, `ci-baseline`,
      `maintenance-task` (o contrato da seção 3 como Preflight/Stop/Checklist).
- [ ] `intelligence_standardizer` passa a instalar `.agents` como submódulo/pointer nos
      repos alvo, para qualquer harness enxergar as mesmas skills.

### Fase 4 — observabilidade

- [ ] Issue de status por repo + digest diário; coluna `token_usage` por run
      (ROADMAP do vibe-code) para provar que o custo ficou em zero.

## 6. Decisões e alternativas

- **Manter o vibe-code, mas encolher.** O que ele já faz bem (worktree isolado,
  concorrência, `dependsOn`, PR + review) é exatamente o runtime que falta ao GA. O
  custo é podar. Alternativa se preferir matar o vibe-code: `opencode_local` + GitHub
  Projects como kanban cobre T0–T2, mas perde concorrência, retry e review.
- **Planner sem LLM.** Detectores determinísticos são testáveis e não gastam token. O
  LLM só entra na execução, dentro do harness.
- **Jules é profile, não engine.** Não vale escrever engine Jules no vibe-code: a
  sessão roda fora, o GA já tem client e tracker.

## 7. Primeiro passo sugerido

Implementar Fase 1 apenas com T0 + T1 e o `idempotencyKey` no vibe-code, apontando
para 2 repos da allowlist. Isso valida a fila, o auto-merge e o fluxo de webhook em
uma semana, antes de tocar em dependências ou migração de stack.
