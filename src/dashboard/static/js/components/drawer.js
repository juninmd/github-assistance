// Job detail drawer: facts, last error, payload, plus reprocess and live "explain".
import { api } from "../api.js";
import { h, icon } from "../dom.js";
import { dateTime } from "../format.js";
import { jobState, statusBadge } from "../status.js";
import { toast } from "./toast.js";

const dialog = document.getElementById("job-drawer");
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});

function fact(term, value) {
  return h("div", null, h("dt", { text: term }), h("dd", { text: value ?? "—" }));
}

function block(title, content) {
  return h("section", { class: "block" }, h("h3", { text: title }), content);
}

function pullRequestUrl(job) {
  const match = /^([\w.-]+\/[\w.-]+)#(\d+)$/.exec(job.key);
  return match ? `https://github.com/${match[1]}/pull/${match[2]}` : null;
}

async function explain(job, slot, button) {
  const [repo, number] = job.key.split("#");
  button.disabled = true;
  try {
    const result = await api(`/prs/${repo}/${number}/explain`);
    slot.replaceChildren(block(`Por que não foi mesclado · decisão: ${result.decision ?? "—"}`,
      h("ul", { class: "reasons" }, (result.reasons?.length ? result.reasons : ["Nenhum impedimento encontrado."]).map((reason) => h("li", null, icon("info"), h("span", { text: reason }))))));
  } catch (error) {
    toast(`Não foi possível explicar: ${error.message}`);
  } finally {
    button.disabled = false;
  }
}

export function openJob(job, { onChange }) {
  const url = pullRequestUrl(job);
  const explained = h("div");
  const explainButton = h("button", { class: "button", type: "button" }, icon("info"), "Explicar decisão");
  explainButton.addEventListener("click", () => explain(job, explained, explainButton));
  const reprocess = h("button", { class: "button", type: "button", disabled: job.status === "running" }, icon("retry"), "Reprocessar");
  reprocess.addEventListener("click", async () => {
    reprocess.disabled = true;
    try {
      const updated = await api(`/jobs/${job.id}/reprocess`, { method: "POST" });
      toast(`${job.key} voltou para a fila`);
      onChange();
      openJob(updated, { onChange });
    } catch (error) {
      toast(`Falha ao reprocessar: ${error.message}`);
      reprocess.disabled = false;
    }
  });
  const close = h("button", { class: "icon-button", type: "button", "aria-label": "Fechar", onclick: () => dialog.close() }, icon("close"));
  dialog.replaceChildren(
    h("header", { class: "drawer-head" },
      h("div", { class: "drawer-title" }, h("h2", { id: "drawer-title", text: job.key }), close),
      h("div", { class: "drawer-actions" }, statusBadge(jobState(job)),
        url ? h("a", { class: "button", href: url, target: "_blank", rel: "noreferrer noopener" }, icon("external"), "Abrir no GitHub") : null,
        reprocess, url ? explainButton : null)),
    h("div", { class: "drawer-body" },
      h("dl", { class: "facts" },
        fact("Repositório", job.repo), fact("Decisão", job.decision), fact("Próxima ação", job.next_action),
        fact("Tentativas", `${job.attempts} de ${job.max_attempts}`), fact("Prioridade", String(job.priority)),
        fact("Evento pendente", job.reprocess_pending ? "sim, reavaliar ao terminar" : "não"),
        fact("Criado", dateTime(job.created_at)), fact("Atualizado", dateTime(job.updated_at)),
        fact("Próxima execução", dateTime(job.next_run_at)), fact("Lease expira", dateTime(job.lease_expires_at)),
        fact("SHA", job.sha), fact("Task ID", job.task_id)),
      explained,
      job.last_error ? block("Último erro", h("pre", { text: job.last_error })) : null,
      block("Payload", h("pre", { text: JSON.stringify(job.payload, null, 2) }))));
  if (!dialog.open) dialog.showModal();
  close.focus();
}
