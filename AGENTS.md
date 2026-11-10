# 🧠 AGENTS.md - Github Assistance Intelligence System

## ⚠️ Regra Obrigatória: Identificação de Origem em PRs e Issues

**Todo pull request ou issue criado por um agente DEVE incluir no corpo:**

```
---
🤖 **Origem Automatizada**
- **Agente:** `<nome-do-agente>`
- **Modelo:** `<modelo-de-ia-utilizado>`
- **Repositório de origem:** [github-assistance](https://github.com/juninmd/github-assistance)
```

Esta regra é **não negociável** e se aplica a:
- PRs criados via `OpencodeRunner._open_pull_request` (`src/agents/opencode/runner.py`)
- PRs criados via `BaseAgent._open_pull_request` (`src/agents/core/base_agent.py`)
- Issues criadas por qualquer agente
- Comentários automáticos em PRs/issues

**Agentes que criam PRs:** `senior_developer`, `ci_health`, `intelligence_standardizer`, `interface_developer`, `conflict_resolver`, `project_creator`, `readme_curator`, `dependency_manager`

---

## 🗺️ Overview

Frota de agentes de IA que mantém um portfólio GitHub em piloto automático.
Todos herdam de `BaseAgent`, são declarados em **uma única tabela**
(`src/agents/core/catalog.py`, `AGENT_CATALOG`) e executados por um único CLI:

```bash
uv run run-agent <agent-name> [--pr owner/repo#N] [--ai-provider P] [--ai-model M]
uv run run-agent all        # todos os agentes habilitados, respeitando dependências
```

Cada agente tem uma pasta em `src/agents/<nome>/` com `agent.py` e
`instructions.md` (seções `## Persona` e `## Mission`). Setup, comandos e
variáveis: [README.md](README.md). Fila durável, política de merge e operação:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 🗂️ Mapa do código

| Caminho | O que mora ali |
|---|---|
| `src/agents/<agente>/` | Um pacote por agente: `agent.py`, `instructions.md` e módulos próprios |
| `src/agents/core/` | Infra compartilhada: `catalog.py` (fonte única), `base_agent.py`, `registry.py`, `orchestration.py`, `batch_runner.py`, `fleet.py`, `reporting.py`, `utils.py` |
| `src/agents/opencode/` | Integração opencode: `models.py`, `local.py`, `runner.py` |
| `src/ai/` | Clientes de IA (SDKs pesados importados sob demanda via `src/utils/lazy_import.py`) |
| `src/queue/` | Fila durável SQLite: `schema.py`, `store.py`, `outcome.py`, `read.py`, `overview.py`, `worker.py` |
| `src/webhooks/` | `server.py` (webhook + lifespan), `admin_api.py` (`/api/*`), `store.py`, `dispatcher.py` |
| `src/dashboard/` | Central de Controle em `/dashboard/`: `static/` com HTML, CSS e ES modules, sem build |
| `src/config/`, `src/insight/`, `src/jules/`, `src/notifications/` | Settings e políticas, explicação de PRs, cliente Jules, Telegram |
| `scripts/` | `benchmark.py`, `seed_demo_queue.py`, checagens de política e dry-runs |

## 👤 Agentes (17 registrados)

Prioridade: **Critical** (segurança) › **High** (bloqueios de PR/CI) › **Medium** › **Low**.
Toggle de cada agente: variável `*_ENABLED` (ver `.env.example`).

### Segurança (Critical)

| Agente | Papel | Notas |
|---|---|---|
| `security-scanner` 🔒 | Gitleaks em todos os repositórios do owner (ignora allowlist, somente leitura); atribui achados ao autor do commit; aplica a política **no-cron-workflow** (`workflow_policy.py`) | Diário 06:00 UTC |
| `secret-remover` 🛡️ | Classifica achados com IA, reescreve o histórico git para remover segredos reais, atualiza allowlist de falsos positivos | Depende de `security-scanner` |

### Pull requests e CI (High)

| Agente | Papel | Notas |
|---|---|---|
| `pr-assistant` 🤖 | Aplica sugestões de revisão (Jules, Gemini Code Assist), atualiza o branch contra a base, corrige CI/conflitos (opt-in), faz **squash merge** via `MergePolicy` | A cada 15 min; trabalha em **todos** os repos do owner |
| `conflict-resolver` ⚔️ | Encontra PRs com conflito e resolve com IA de forma segura | Sempre habilitado |
| `code-reviewer` 👀 | Revisão de PRs: qualidade, bugs, segurança, performance | |
| `ci-health` ⚕️ | Monitora pipelines, detecta falhas/flaky e dispara remediação | |
| `pr-sla` ⏱️ | Idade/tempo de revisão de PRs, alerta de PRs paradas | Low |

### Desenvolvimento e documentação (Medium/Low)

| Agente | Papel | Notas |
|---|---|---|
| `senior-developer` 🏗️ | Análise de segurança, CI/CD, dívida técnica, modernização e roadmap; faz `git pull` da branch principal antes de implementar | Semanal; burst no fim do dia |
| `dependency-manager` 📦 | Detecta ecossistemas (node/python/go/rust/php); CVEs primeiro, depois patch/minor (nunca major inseguro); atualiza lockfile, roda testes, abre **um** PR agrupado via opencode | |
| `readme-curator` 📚 | Varre todos os repos do owner (sem allowlist; ignora arquivados e forks), do README mais antigo para o mais novo; reescreve os ausentes, com mais de 6 meses (`README_MAX_AGE_DAYS`, 180) ou abaixo de `README_MIN_SCORE` (80); sempre em inglês | |
| `intelligence-standardizer` 🧬 | Garante `AGENTS.md` + `.agents/` nos 10 repos mais recentes, boas práticas (KISS, YAGNI, DRY, SRP) e limite de linhas | Diário |
| `product-manager` 📋 | Backlog, roadmap e documentação de produto | Low |
| `interface-developer` 🎨 | UI/UX, acessibilidade e responsividade via tarefas Jules | Low |
| `project-creator` 🚀 | Gera ideia ancorada no portfólio real do dono (repos feitos à mão = padrão; autogerados = anti-exemplo; critério `fit` ≥ 4), cria repositório privado e inicia sessão Jules | Low; semanal domingo 00:00 UTC |

### Higiene e Jules

| Agente | Papel | Notas |
|---|---|---|
| `branch-cleaner` 🧹 | Remove branches já mergeadas (nunca a principal, nunca branches com PR aberto) | |
| `jules-tracker` 🔍 | Monitora sessões Jules; responde perguntas e aprova/ajusta planos via LiteLLM (`_handle_plan_approval`) | Cluster |
| `jules-cleaner` 🗑️ | Apaga sessões Jules mais velhas que `JULES_CLEANER_MAX_AGE_DAYS` (padrão 3) | Cluster |

> O estado Jules de "aguardando aprovação de plano" nunca foi observado ao vivo
> (só `IN_PROGRESS` e `AWAITING_USER_FEEDBACK`, via `tests/smoke/test_jules_e2e_smoke.py`).
> `is_plan_approval_state` usa *pattern matching* (`PLAN`+`APPROV`, ou `PENDING`
> + plano pendente); ajuste-o se o formato real divergir.

### Ideias ainda não implementadas
Performance Optimizer ⚡ (gargalos, bundle size), Documentation Curator 📚
(docs de API, cobertura de docs), Test Coverage Guardian 🧪 (caminhos sem teste).

## 📜 Development Rules (Antigravity Protocol)

1. **Size Limit**: máx. **150 linhas por arquivo** (meta; vários módulos ainda excedem — ver ROADMAP)
2. **Clean Logic**: separação de responsabilidades em todas as camadas
3. **Validation**: toda mudança exige testes e lint passando (`ruff`, `pyright`, `pytest`)
4. **Security**: dados sensíveis fora do contexto de IA
5. **Type Safety**: tipagem forte, evitar tipos dinâmicos
6. **Testing**: cobertura alta (gate de CI em 80%, meta 100%)
7. **DRY/KISS/SOLID**: aplicados com rigor
8. **Merge Method**: **sempre squash merge**, histórico limpo

## 🤝 Agent Interaction Protocol

- **Ciclo**: Plan → Act (ou delegar ao Jules/opencode) → Validate → Communicate.
- **Canais**: resultados em `results/*.json`; Telegram como hub de notificações; PRs/issues/comentários no GitHub; Jules para trabalho de código complexo.
- **Coordenação**: agentes não se chamam diretamente. Dependências declaradas em `src/agents/core/orchestration.py` (hoje: `secret-remover` → `security-scanner`). `validate()` rejeita dependências ausentes e ciclos; um dependente só roda se a dependência realmente teve sucesso.
- **Exclusividade**: a fila durável garante um job por `(kind, key)`; labels de PR e deduplicação de sessões Jules evitam trabalho sobreposto.
- **Resultado tipado**: todo run gera `RunResult` (`src/results.py`); `run-agent all` sai com erro se algum agente falhar. PRs bloqueadas por CI pendente/observe não contam como falha.

### Quotas
GitHub API 5.000 req/h (monitorado pelo `BaseAgent`); Jules 100 sessões/dia com burst no fim do dia; Telegram com rate limit no notifier.

## ☸️ Execução em produção (Kubernetes)

- Rotinas periódicas — em especial `jules-tracker`, `jules-cleaner` e o pipeline diário projeto/Jules — rodam como **CronJob/Job no cluster**, nunca despachadas manualmente via GitHub Actions.
- GitHub Actions mantém só CI e checagens de política. **Não use `gh workflow run`** como smoke test de rotinas Jules.
- **Nenhum workflow com `on: schedule`/`cron`** neste repo (`scripts/check_no_cron_workflows.py` no CI; o Security Scanner aplica a mesma política ao portfólio).
- Imagem: `Dockerfile` (Python + Node + `opencode` + `gitleaks`, usuário não-root, `tini`); comando padrão `run-agent pr-assistant`.
- Servidor de webhooks (`webhook-server`) + worker (`queue-worker`): **uma réplica** (escritor SQLite único).
- LiteLLM: o runner do GitHub não alcança o endereço interno `litellm.ai.svc.cluster.local`; fora do cluster configure `LITELLM_API_BASE` para o ingress público (com `/v1`) e `LITELLM_API_KEY` com uma virtual key.

### Pendências de homologação
- [ ] Validar `POST /v1/chat/completions` real com a virtual key do LiteLLM.
- [ ] Rodar o CronJob/Job real: criação de repo, sessão Jules e observar o `state` de aprovação de plano.
- [ ] Rotacionar/revogar a virtual key se não for mais necessária.

## 🧾 Merge Gate e falhas de billing do CI

Quando o GitHub Actions se recusa a iniciar um job por billing ("recent account
payments have failed", "spending limit needs to be increased"), o job **nunca
rodou** — é problema de conta, não de código. Por decisão do owner, isso **não
bloqueia o merge**:

- `pipeline.py::check_pipeline_status` conta a falha com padrão de billing como **passed** e a lista em `billing_checks`; nunca entra em `failed_checks`.
- Qualquer outra falha real no mesmo SHA continua bloqueando.
- `merge_policy.py` não tem motivo específico de billing.
- Merge autônomo exige `AUTOMATION_MODE=autonomous` **e** política do repo `mode=merge, merge=true` (`config/autonomy.json`); evidência ausente/pendente/cancelada nunca vira merge, e o merge usa `expected_sha`.

## 🧩 opencode (opt-in)

- Resolução de conflitos com opencode: `CONFLICT_OPENCODE_ENABLED=true` (padrão desligado).
- Correção de pipeline com opencode: `PIPELINE_FIX_ENABLED=true` (padrão desligado).
- `SIMULATION_MODE=true` registra todas as decisões sem nenhuma escrita externa.

## 🛠️ Agent Development Guidelines

### Criar um novo agente
1. Criar `src/agents/<nome>/` com `__init__.py`, `agent.py` (herda de `BaseAgent`; implementa `persona`, `mission`, `run()`) e `instructions.md` (`## Persona`, `## Mission`).
2. Adicionar **um** `AgentSpec` em `src/agents/core/catalog.py` (prioridade, toggle, IA/Jules/Telegram, dependências). Registry, batch runner, orquestrador, health checks, entry points e dashboard derivam dele.
3. Se tiver toggle: campo `enable_<nome>` em `Settings` e a variável em `.env.example`; entry point em `pyproject.toml` (`<nome> = "src.scripts:<nome_com_underscore>"`).
4. Escrever testes e atualizar este arquivo e o README. `tests/test_agent_catalog.py` falha se algum passo faltar.

### Boas práticas
Responsabilidade única; usar os clients compartilhados (GitHub, Jules, Telegram); logar ações importantes; tratar erros com graça; respeitar rate limits; salvar resultados em JSON; notificar eventos relevantes no Telegram.

## 🔐 Security Considerations

- Segredos apenas por variáveis de ambiente; nunca enviar dados sensíveis a modelos de IA.
- Sanitizar saídas antes de logar.
- A allowlist (`config/repositories.json`) limita onde os agentes modificam código; `security-scanner` e `readme-curator` varrem o portfólio sem ela (o scanner somente leitura).
- Operações git sensíveis são feitas localmente, não via Jules.
- Só comentários de `OWNER`/`MEMBER`/`COLLABORATOR` chegam ao avaliador LLM do merge; um erro/ausência do avaliador resulta em `wait`, nunca em merge.
- Rotas `/api/*` exigem `Authorization: Bearer $ADMIN_API_TOKEN` (403 se não configurado).
- O dashboard (`/dashboard/`) é uma casca estática sem dados: CSP `default-src 'none'`, nenhum script/estilo inline nem origem externa, texto sempre via `textContent`; o token fica só no `sessionStorage` da aba. `DASHBOARD_ENABLED=false` remove a rota.

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