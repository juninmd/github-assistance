import { h, icon } from "../dom.js";
import { num } from "../format.js";
import { toast } from "../components/toast.js";

const PRIORITIES = [["critical", "Crítica · segurança"], ["high", "Alta · PRs e CI"], ["medium", "Média"], ["low", "Baixa"]];
const TAGS = [["requires_ai", "IA"], ["uses_jules", "Jules"], ["notifies_telegram", "Telegram"], ["accepts_pr_ref", "--pr"]];

function agentCard(agent, index) {
  const command = `uv run run-agent ${agent.name}`;
  const copy = h("button", { class: "icon-button", type: "button", "aria-label": `Copiar comando de ${agent.name}`, title: command }, icon("copy"));
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(command);
      toast("Comando copiado");
    } catch {
      toast(command);
    }
  });
  return h("article", { class: "card agent", "data-runnable": String(agent.runnable), style: { "--order": String(index) } },
    h("div", { class: "agent-head" },
      h("span", { class: "agent-emoji", "aria-hidden": "true", text: agent.emoji }),
      h("div", null, h("p", { class: "agent-name", text: agent.name }),
        h("span", { class: "pill", "data-tone": agent.runnable ? "good" : "warning" },
          icon(agent.runnable ? "check" : "info"), agent.runnable ? "Apto a rodar" : `Parado · ${agent.blocked_reason}`)),
      h("div", { class: "card-tools", style: { "margin-left": "auto" } }, copy)),
    h("p", { class: "subtle", text: agent.summary }),
    h("div", { class: "agent-tags" },
      TAGS.filter(([key]) => agent[key]).map(([, label]) => h("span", { class: "tag", text: label })),
      agent.in_batch ? null : h("span", { class: "tag", text: "fora do all" }),
      agent.depends_on.map((name) => h("span", { class: "tag", text: `depois de ${name}` }))));
}

export function createFleet(root) {
  const summary = h("p");
  const groups = h("div", { class: "grid" });
  root.replaceChildren(
    h("header", { class: "view-head" }, h("div", null, h("h1", { id: "fleet-title", text: "Frota" }), summary)),
    groups);

  function update({ agents, ai, owner }) {
    const runnable = agents.filter((agent) => agent.runnable).length;
    summary.textContent = `${num(agents.length)} agentes cuidando de ${owner} · ${num(runnable)} aptos a rodar · IA ${ai.enabled ? `ligada (${ai.provider} / ${ai.model})` : "desligada"}.`;
    groups.replaceChildren(...PRIORITIES.flatMap(([priority, title]) => {
      const members = agents.filter((agent) => agent.priority === priority);
      if (!members.length) return [];
      return [
        h("h2", { class: "group-title" }, title, h("span", { class: "tag", text: num(members.length) })),
        h("div", { class: "grid cards" }, members.map(agentCard)),
      ];
    }));
  }

  return { update };
}
