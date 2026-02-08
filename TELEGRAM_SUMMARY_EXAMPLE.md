# 📊 Exemplo de Resumo do Telegram

## Resumo Completo com Todas as Categorias

Quando o PR Assistant finaliza um ciclo, ele envia uma mensagem organizada no Telegram:

---

### 📊 **PR Assistant Summary**

**🔍 Total Analisados:** 8
**✅ Mergeados:** 2
**🛠️ Conflitos Resolvidos:** 1
**❌ Falhas de Pipeline:** 1
**📝 Draft:** 2
**⏩ Pulados/Pendentes:** 2

👤 Dono: `juninmd`

---

### ✅ **PRs Mergeados:**
• [agar#12](https://github.com/juninmd/agar/pull/12) - Fix database connection pool leak
• [website#45](https://github.com/juninmd/website/pull/45) - Update dependencies to latest versions

---

### 🛠️ **Conflitos Resolvidos:**
• [api-server#23](https://github.com/juninmd/api-server/pull/23) - Merge conflicts detected, comment posted

---

### ❌ **Falhas de Pipeline:**
• [mobile-app#67](https://github.com/juninmd/mobile-app/pull/67) - Add unit tests for authentication module
• [backend#89](https://github.com/juninmd/backend/pull/89) - Refactor payment processing logic

---

### 📝 **PRs em Draft:**
• [agar#16](https://github.com/juninmd/agar/pull/16) - Refactor Core Architecture & Add Protocol...
• [ball-x-pitt#16](https://github.com/juninmd/ball-x-pitt/pull/16) - Core Mechanics and DevOps for NeonDefense

---

### ⏩ **Pulados/Pendentes:**
• [frontend#34](https://github.com/juninmd/frontend/pull/34) - Improve loading performance (pipeline_pending)
• [docs#11](https://github.com/juninmd/docs/pull/11) - Update API documentation (mergeability_unknown)

---

## Características do Resumo

### 📋 **Informações por PR:**
- **Repositório curto:** `repo#123` (sem username)
- **Link clicável:** Clique direto no número do PR
- **Título resumido:** Até 45 caracteres + "..."
- **Motivo (quando aplicável):** Pipeline_pending, unauthorized_author, etc.

### 🎯 **Categorização Inteligente:**
1. **✅ Mergeados:** PRs que foram merged com sucesso
2. **🛠️ Conflitos:** PRs com conflitos identificados (comentário postado)
3. **❌ Pipeline:** PRs com falhas no CI/CD
4. **📝 Draft:** PRs marcados como draft (work in progress)
5. **⏩ Pulados:** PRs que não puderam ser processados (com motivo)

### 🔗 **Links Diretos:**
Todos os PRs incluem links clicáveis que levam direto ao PR no GitHub, facilitando navegação e revisão rápida.

### 📱 **Formato Mobile-Friendly:**
O resumo é formatado com Markdown do Telegram para melhor legibilidade em dispositivos móveis.

---

## Notificação Individual de Merge

Quando um PR é mergeado, você também recebe uma notificação individual:

---

### 🚀 **PR Merged!**

**Title:** Fix database connection pool leak
**Repository:** juninmd/agar
**Author:** juninmd

**Description:**
This PR fixes a critical issue where database connections were not being properly returned to the pool, causing connection exhaustion under high load...

**[Botão: 🔗 Ver PR]** ← Clique aqui para abrir o PR

---

## Benefícios

✅ **Visão completa** de todos os PRs processados
✅ **Navegação rápida** com links diretos
✅ **Context rico** com títulos e motivos
✅ **Organização clara** por categoria
✅ **Mobile-friendly** para acompanhamento em qualquer lugar
✅ **Botões interativos** para ação rápida
