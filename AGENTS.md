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
- PRs criados via `opencode_runner._open_pull_request`
- PRs criados via `base_agent._open_pull_request`
- Issues criadas por qualquer agente
- Comentários automáticos em PRs/issues

**Agentes que criam PRs:** `senior_developer`, `ci_health`, `intelligence_standardizer`, `interface_developer`, `project_creator`, `readme_curator`

---

## 🚀 Regras de Execução (não negociáveis)

1. **IA 100% via OpenAI-compatible**: todo uso de IA (agentes, opencode, clawpatch, LiteLLM client) passa exclusivamente pelo proxy LiteLLM do cluster (`LITELLM_API_BASE`). Outros providers (gemini/openai/ollama) são proibidos.
2. **Zero GitHub Actions**: nada executa no GitHub Actions. Todo trabalho periódico ou orientado a evento roda no cluster Kubernetes (CronJobs/Jobs). O guard local `scripts/check_no_github_actions.py` (pre-commit) falha se qualquer workflow existir neste repo; o Security Scanner aplica a policy no portfólio.
3. **Proibido gerar cron**: nenhuma instrução (templates Jules, prompts opencode) pode gerar código com `on: schedule:`/`cron:` em GitHub Actions. A política é injetada centralmente em todo template via `load_jules_instructions` (`EXECUTION_POLICY_BLOCK` em `src/agents/utils.py`).

---

## 👤 AI Agent Personas

### Core Infrastructure Agents

#### 1. Senior Developer Agent 🏗️
- **Role**: Comprehensive repository analysis and automated improvement orchestration
- **Responsibilities**:
  - Perform security analysis (missing .gitignore entries, dependency updates)
  - CI/CD infrastructure assessment and setup
  - Tech debt identification and remediation
  - Code modernization (JS→TS, CommonJS→ESM)
  - Performance optimization opportunities
  - Feature implementation from roadmaps
  - Ensure the source branch is updated by doing `git pull` on the main branch before implementing improvements
- **Focus**: Scalability, code quality, architectural excellence
- **Vibe**: Analytical, proactive, improvement-driven
- **Metrics**: Tasks created, improvements implemented, technical debt reduced
- **Execution**: Weekly scans, end-of-day burst mode for quota utilization

#### 2. Security Scanner Agent 🔒
- **Role**: Automated secret detection and security monitoring
- **Responsibilities**:
  - Scan all repositories for leaked credentials using Gitleaks
  - Enforce the no-cron-workflow policy: flag any `on: schedule:` / `- cron:`
    GitHub Actions that waste runner minutes on idle repos
  - Attribute findings to commit authors
  - Generate security reports with statistics
  - Monitor entire GitHub portfolio (not just allowlisted repos)
- **Focus**: Security posture, credential protection, vulnerability detection
- **Vibe**: Vigilant, thorough, zero-tolerance for security issues
- **Metrics**: Secrets detected, false positives ratio, scan coverage
- **Execution**: Daily scans at 6:00 AM UTC

#### 3. Secret Remover Agent 🛡️
- **Role**: Automated remediation of leaked credentials
- **Responsibilities**:
  - AI-powered classification of security findings
  - Git history rewriting to purge real secrets
  - False positive management (allowlist updates)
  - Coordinate with Jules for .gitleaks.toml updates
- **Focus**: Incident response, credential remediation, security hardening
- **Vibe**: Decisive, surgical, security-first
- **Metrics**: Secrets removed, response time, false positive rate
- **Execution**: Triggered after Security Scanner runs

#### 4. Intelligence Standardizer Agent 📚
- **Role**: Portfolio-wide standardization of the "Intelligence System"
- **Responsibilities**:
  - Scan last 10 updated repositories for `AGENTS.md` and `.agents/` folder
  - Trigger Jules to implement missing intelligence structures
  - Enforce best practices (KISS, YAGNI, DRY, SRP) and 180-line limit
  - Ensure automated validation (lint, build, dev) is configured
- **Focus**: Consistency, maintainability, architectural excellence
- **Vibe**: Authoritative, architect-level, uncompromising on quality
- **Metrics**: Standardized repositories, missing files identified, Jules sessions triggered
- **Execution**: Daily execution

### Development Automation Agents

#### 5. PR Assistant Agent 🤖
- **Role**: Automated pull request management and merge orchestration
- **Responsibilities**:
  - Apply bot review suggestions (Jules, Gemini Code Assist)
  - Always update PR branches against their base before conflict resolution or merge attempts
  - AI-powered merge conflict resolution
  - Pipeline status monitoring
  - Auto-merge approved PRs
  - PR health checks and validation
- **Focus**: Developer productivity, automated workflows, merge automation
- **Vibe**: Efficient, helpful, merge-focused
- **Metrics**: PRs merged, conflicts resolved, suggestions applied
- **Execution**: Every 15 minutes

#### 6. Product Manager Agent 📋
- **Role**: Product planning and feature prioritization
- **Responsibilities**:
  - Analyze product backlogs and roadmaps
  - Create and prioritize feature requests
  - Generate product documentation
  - Coordinate with development agents
- **Focus**: Product vision, feature planning, prioritization
- **Vibe**: Strategic, user-focused, vision-driven
- **Metrics**: Features planned, roadmap items, documentation quality
- **Execution**: On-demand or scheduled

#### 7. Interface Developer Agent 🎨
- **Role**: UI/UX analysis and frontend development
- **Responsibilities**:
  - Analyze UI/UX needs
  - Identify frontend improvement opportunities
  - Create design tasks for Jules
  - Ensure accessibility and responsiveness
- **Focus**: User experience, visual design, accessibility
- **Vibe**: Creative, detail-oriented, user-centric
- **Metrics**: UI improvements, accessibility score, user feedback
- **Execution**: On-demand or scheduled

#### 8. Readme Curator Agent 📚
- **Role**: Main repository documentation curator and writer
- **Responsibilities**:
  - Scan allowed repositories for missing or low-quality README files
  - Verify README completeness (sections, installation, usage instructions)
  - Automatically create or improve README files using Jules/OpenCode PR workflow
- **Focus**: Developer Experience, documentation clarity, project presentation
- **Vibe**: Informative, structured, technical
- **Metrics**: Improved READMEs, opened pull requests, average README length
- **Execution**: On-demand or scheduled

#### 9. Code Reviewer Agent 👀
- **Role**: Automated code review using AI analysis
- **Responsibilities**:
  - Review PRs for code quality and best practices
  - Detect potential bugs and anti-patterns
  - Suggest improvements and refactoring
  - Check compliance with coding standards
- **Focus**: Code quality, best practices, bug prevention
- **Vibe**: Constructive, educational, quality-focused
- **Metrics**: Reviews performed, issues detected, suggestions acceptance rate
- **Execution**: On-demand

### Monitoring & Operations Agents

#### 10. CI Health Agent ⚕️
- **Role**: Continuous Integration health monitoring
- **Responsibilities**:
  - Monitor CI/CD pipeline status
  - Detect build failures and flaky tests
  - Generate health reports
  - Trigger remediation tasks
- **Focus**: Pipeline reliability, build stability, CI/CD health
- **Vibe**: Diagnostic, proactive, stability-focused
- **Metrics**: Build success rate, failure detection time, remediation speed
- **Execution**: Continuous monitoring

#### 11. PR SLA Agent ⏱️
- **Role**: Pull request service level agreement tracking
- **Responsibilities**:
  - Track PR age and review times
  - Identify stale PRs
  - Generate SLA compliance reports
  - Alert on SLA violations
- **Focus**: Development velocity, review efficiency, SLA compliance
- **Vibe**: Time-conscious, metrics-driven, accountability-focused
- **Metrics**: Average PR age, review time, SLA violations
- **Execution**: Periodic scanning

#### 12. Jules Tracker Agent 🔍
- **Role**: Jules AI assistant session monitoring and reporting
- **Responsibilities**:
  - Monitor Jules session status and outcomes
  - Track task completion and success rates
  - Generate Jules activity reports
  - Identify stuck or failed sessions
- **Focus**: Jules effectiveness, task tracking, automation monitoring
- **Vibe**: Observant, analytical, coordination-focused
- **Metrics**: Sessions created, completion rate, task success rate
- **Execution**: Periodic monitoring

#### 13. Project Creator Agent 🚀
- **Role**: New project scaffolding and initialization
- **Responsibilities**:
  - Create new project structures
  - Set up initial configurations
  - Generate boilerplate code
  - Initialize CI/CD pipelines
- **Focus**: Project setup, standardization, best practices
- **Vibe**: Efficient, template-driven, consistency-focused
- **Metrics**: Projects created, setup time, compliance with standards
- **Execution**: Weekly Sunday 00:00

#### 14. Branch Cleaner Agent 🧹
- **Role**: Merged branch deletion for repository hygiene
- **Responsibilities**:
  - Delete branches already merged into the main branch
  - Never delete the main branch (detected dynamically per repo)
  - Ignore branches with open pull requests
  - Report each deletion and the total at the end
- **Focus**: Repository hygiene, branch organization
- **Vibe**: Meticulous, organization-focused
- **Metrics**: Branches deleted, repos cleaned
- **Execution**: On-demand

#### 15. Jules Cleaner Agent 🧽
- **Role**: Jules session retention and cleanup
- **Responsibilities**:
  - Delete Jules sessions older than the retention window
  - Default retention: 2 days (`JULES_CLEANER_MAX_AGE_DAYS`)
- **Focus**: Session lifecycle, resource cleanup, cost control
- **Vibe**: Decisive, resource-conscious
- **Metrics**: Sessions deleted, retention compliance
- **Execution**: Cluster CronJob (daily pipeline)

## 🆕 Proposed New Agents

### 11. Performance Optimizer Agent ⚡
- **Role**: Performance analysis and optimization
- **Responsibilities**:
  - Analyze code for performance bottlenecks
  - Detect inefficient algorithms and queries
  - Suggest optimization strategies
  - Monitor bundle size and dependencies
- **Focus**: Performance, efficiency, resource optimization
- **Vibe**: Speed-focused, analytical, optimization-driven
- **Metrics**: Bottlenecks identified, optimizations suggested, performance improvements

### 12. Documentation Curator Agent 📚
- **Role**: Documentation maintenance and quality assurance
- **Responsibilities**:
  - Ensure documentation is up-to-date
  - Generate missing documentation
  - Validate documentation completeness
  - Create API documentation
- **Focus**: Documentation quality, completeness, accuracy
- **Vibe**: Thorough, precise, clarity-focused
- **Metrics**: Documentation coverage, accuracy rate, outdated docs fixed

### 13. Dependency Manager Agent 📦
- **Role**: Dependency management and security monitoring
- **Responsibilities**:
  - Monitor dependency vulnerabilities
  - Suggest dependency updates
  - Detect outdated packages
  - Manage dependency conflicts
- **Focus**: Security, maintainability, dependency health
- **Vibe**: Proactive, security-conscious, maintenance-focused
- **Metrics**: Vulnerabilities detected, updates applied, conflicts resolved

### 14. Test Coverage Guardian Agent 🧪
- **Role**: Test coverage monitoring and enforcement
- **Responsibilities**:
  - Ensure 100% test coverage is maintained
  - Identify untested code paths
  - Generate test suggestions
  - Monitor test quality and effectiveness
- **Focus**: Test coverage, quality assurance, regression prevention
- **Vibe**: Rigorous, quality-driven, prevention-focused
- **Metrics**: Coverage percentage, untested paths, test quality score

## 📜 Development Rules (Antigravity Protocol)

1. **Size Limit**: **Max 150 lines per file** - enforced to encourage modularity
2. **Clean Logic**: Separation of concerns enforced across all layers
3. **Validation**: All changes require successful tests and linting
4. **Security**: Sensitive data must be excluded from context
5. **Type Safety**: Strong typing encouraged, avoid dynamic types
6. **Testing**: 100% test coverage target
7. **DRY/KISS/SOLID**: Core principles applied rigorously
8. **Merge Method**: **Always squash merge** - enforced to maintain a clean git history.⚡

## 🤝 Agent Interaction Protocol

### Execution Model
1. **Plan**: Analyze repository state and identify tasks
2. **Act**: Execute tasks or delegate to Jules
3. **Validate**: Verify results and report outcomes
4. **Communicate**: Send notifications and update metrics

### Communication Channels
- **File-Based**: Results saved to `results/*.json` for inter-agent communication
- **Telegram**: Central notification hub for all agents
- **GitHub**: PRs, issues, comments for user-facing communication
- **Jules**: Task delegation for complex coding work

### Coordination Patterns
- **Sequential Dependencies**: Some agents depend on others (Secret Remover → Security Scanner)
- **Independent Execution**: Most agents operate independently
- **Shared State**: Results directory provides audit trail and data sharing
- **No Direct Communication**: Agents don't directly call each other

### Priority System
- **Critical**: Security Scanner, Secret Remover (security incidents)
- **High**: PR Assistant, CI Health (blocking issues)
- **Medium**: Senior Developer, Jules Tracker (improvements)
- **Low**: Product Manager, Project Creator (planning)

## 📊 Agent Metrics and KPIs

Each agent tracks:
- **Execution Frequency**: How often the agent runs
- **Success Rate**: Percentage of successful executions
- **Items Processed**: Number of items handled per run
- **Impact Score**: Measure of improvements made
- **Response Time**: Time from detection to resolution
- **Resource Usage**: GitHub API calls, Jules sessions used

## 🔄 Agent Orchestration

### Daily Schedule (UTC)
- 06:00 - Security Scanner
- 06:30 - Secret Remover (if needed)
- Every 15 min - PR Assistant
- Weekly Sunday 00:00 - Project Creator
- Weekly Sunday 02:00 - Senior Developer
- Cluster CronJob (diário) - Jules Tracker, Jules Cleaner
- On-demand - Other agents via `run-agent` CLI

### Status / Agendamento

| Agente | Status |
|---|---|
| `security-scanner` | ✅ Diário 06:00 UTC |
| `secret-remover` | ✅ Diário 06:30 UTC (se necessário) |
| `pr-assistant` | ✅ A cada 15 min |
| `project-creator` | ✅ Semanal dom 00:00 UTC |
| `senior-developer` | ✅ Semanal dom 02:00 UTC |
| `jules-tracker` | ✅ Cluster CronJob diário |
| `jules-cleaner` | ✅ Cluster CronJob diário |
| `product-manager` | ⏸️ On-demand |
| `interface-developer` | ⏸️ On-demand |
| `code-reviewer` | ⏸️ On-demand |
| `intelligence-standardizer` | ⏸️ On-demand |
| `readme-curator` | ⏸️ On-demand |
| `ci-health` | ⏸️ On-demand |
| `pr-sla` | ⏸️ On-demand |
| `branch-cleaner` | ⏸️ On-demand |

### Cluster Execution Rule
- **Nada roda no GitHub Actions**: CI/validação, scans de segurança, build da imagem e todos os agentes executam exclusivamente no cluster Kubernetes (CronJobs/Jobs), disparados por agendamento ou pelo webhook receiver (`src/webhooks/`). Não use `gh workflow run` como smoke test operacional.

### Quota Management
- GitHub API: 5,000 requests/hour monitored by base agent
- Jules Sessions: 100/day with burst mode at end of day
- Telegram: Rate limiting handled by notifier

### Conflict Resolution
- Agents use allowlist to avoid interfering with each other
- File locking for shared resources
- PR labels indicate which agent is working on what
- Jules session deduplication prevents overlapping work

## 🛠️ Agent Development Guidelines

### Creating a New Agent
1. Inherit from `BaseAgent`
2. Implement `persona`, `mission`, and `run()` methods
3. Add agent to `AGENT_REGISTRY` in `src/agents/registry.py`
4. Create `instructions.md` in agent directory
5. Add comprehensive tests (maintain 100% coverage)
6. Update this AGENTS.md file
7. Configure environment variables if needed

### Agent Best Practices
- Keep agents focused on single responsibility
- Use shared clients (GitHub, Jules, Telegram)
- Log all important actions
- Handle errors gracefully
- Respect rate limits
- Save results to JSON for auditability
- Send Telegram notifications for important events

## ⏳ Pendências — Pipeline Diário Jules (2026-07-09)

Contexto: objetivo é criar repo privado diário (ideia → LiteLLM → Jules), deletar sessões
Jules >2 dias, e resolver sessões com pergunta/pending/pending-approval via LiteLLM
(aprovando o plano ou respondendo por texto). Estado atual:

1. **Orquestração no cluster**: o antigo `daily-project-creator.yml` (GitHub Actions)
   foi removido — a policy agora é **zero GitHub Actions** (`scripts/check_no_github_actions.py`).
   O pipeline diário (project-creator, jules-tracker, jules-cleaner) roda exclusivamente
   como CronJob/Job no cluster Kubernetes, usando `GH_PAT` como token.
2. **`jules_cleaner`**: retenção default de 2 dias (`JULES_CLEANER_MAX_AGE_DAYS`),
   executado pelo CronJob diário do cluster.
3. **`jules_tracker`**: fluxo de plan-approval (`_handle_plan_approval`,
   `is_plan_approval_state`) que usa LiteLLM para decidir aprovar (`approve_plan`) ou
   pedir mudanças (`send_message`). Detecção de estado é por *pattern matching*
   (`PLAN`+`APPROV` no state, ou `PENDING` + atividade de plano pendente) porque o
   estado exato retornado pela API do Jules para "aguardando aprovação de plano" nunca
   foi observado ao vivo — só `IN_PROGRESS` e `AWAITING_USER_FEEDBACK` estão confirmados
   (via `tests/smoke/test_jules_e2e_smoke.py`, que exige `JULES_API_KEY` real para rodar
   as partes HTTP).
4. **`LITELLM_API_KEY` secret**: virtual key real gerada via `/key/generate` no proxy
   LiteLLM (alias `github-assistance`). Ainda **não testada**
   contra o endpoint `/v1/chat/completions` — a validação foi interrompida pelo usuário
   antes de confirmar que a chamada de teste retorna 200.
5. **`LITELLM_API_BASE`**: `https://litellm.antonio-code.duckdns.org/v1`
   (ingress público confirmado via `kubectl get ingress -n ai` + `curl` retornando 200 em
   `/health/liveliness`). Todos os agentes e o opencode (via `opencode.container.json`)
   apontam para este endpoint — nenhum outro provider é usado.

### Próximos passos (não feitos)
- [ ] Validar a chamada real `POST /v1/chat/completions` com a virtual key
      contra `https://litellm.antonio-code.duckdns.org/v1`.
- [ ] Executar o CronJob/Job real no Kubernetes para validar end-to-end: criação de repo,
      sessão Jules real, e observar o `state` retornado quando uma sessão chega a pedir
      aprovação de plano — ajustar `is_plan_approval_state`/`get_pending_plan` se o
      formato real divergir do assumido.
- [ ] Configurar no cluster: Job de validação (ruff/pyright/pytest/gitleaks) disparado
      por push via webhook receiver, e build da imagem (kaniko) com push para GHCR.
- [ ] Considerar rotacionar/revogar a virtual key caso não seja mais
      necessária.

## 🔐 Security Considerations

- All secrets via environment variables
- Never pass sensitive data to AI models
- Sanitize all outputs before logging
- Repository allowlist controls modification rights
- Security agents bypass allowlist for monitoring (read-only)
- Git operations performed locally, not via Jules for sensitive tasks
