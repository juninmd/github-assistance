import { api, query } from "../api.js";
import { openJob } from "../components/drawer.js";
import { h, icon } from "../dom.js";
import { ago, dateTime, num } from "../format.js";
import { STATUS, jobState, statusBadge } from "../status.js";

const PAGE = 25;
const FILTERS = ["pending", "running", "succeeded", "blocked"];

export function createJobs(root) {
  const state = { status: null, q: "", offset: 0 };
  let signatures = new Map();
  let debounce;
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Filtrar por estado" });
  const search = h("input", { type: "search", placeholder: "Buscar PR (owner/repo#123)", "aria-label": "Buscar PR" });
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => { state.q = search.value.trim(); state.offset = 0; load(); }, 250);
  });
  const body = h("tbody");
  const table = h("table", { class: "table" },
    h("thead", null, h("tr", null,
      h("th", { scope: "col", text: "Pull request" }), h("th", { scope: "col", text: "Estado" }),
      h("th", { scope: "col", text: "Decisão" }), h("th", { scope: "col", class: "optional", text: "Próxima ação" }),
      h("th", { scope: "col", class: "end optional", text: "Tentativas" }), h("th", { scope: "col", class: "end", text: "Atualizado" }))),
    body);
  const empty = h("div", { class: "empty", hidden: true });
  const summary = h("span", { class: "num" });
  const previous = h("button", { class: "button", type: "button", text: "Anterior", onclick: () => page(-1) });
  const next = h("button", { class: "button", type: "button", text: "Próxima", onclick: () => page(1) });
  const panel = h("article", { class: "card" },
    h("div", { class: "table-wrap" }, table, empty, h("div", { class: "pager" }, summary, h("span", { class: "spacer" }), previous, next)));
  root.replaceChildren(
    h("header", { class: "view-head" }, h("div", null, h("h1", { id: "jobs-title", text: "Fila" }),
      h("p", { text: "Um job por pull request. Abra uma linha para ver o motivo, o payload e reprocessar." })),
      h("div", { class: "view-tools" }, h("label", { class: "search" }, icon("search"), search))),
    chips, panel);

  function page(direction) {
    state.offset = Math.max(0, state.offset + direction * PAGE);
    load();
  }

  function paintChips(totals = {}) {
    const all = Object.values(totals).reduce((sum, value) => sum + value, 0);
    const chip = (key, label, count) => h("button", { class: "chip", type: "button", "aria-pressed": String(state.status === key),
      onclick: () => { state.status = key; state.offset = 0; load(); } }, label, h("span", { class: "count", text: num(count) }));
    chips.replaceChildren(chip(null, "Todos", all), ...FILTERS.map((key) => chip(key, STATUS[key].label, totals[key] ?? 0)));
  }

  function row(job, changed) {
    const open = () => openJob(job, { onChange: load });
    return h("tr", { tabindex: "0", class: changed ? "changed" : null, onclick: open,
      onkeydown: (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } } },
      h("td", null, h("span", { class: "job-key", text: job.key })),
      h("td", null, statusBadge(jobState(job))),
      h("td", { text: job.decision ?? "—" }),
      h("td", { class: "optional subtle", text: job.next_action ?? "—" }),
      h("td", { class: "end num optional", text: `${job.attempts}/${job.max_attempts}` }),
      h("td", { class: "end subtle", text: ago(job.updated_at), title: dateTime(job.updated_at) }));
  }

  async function load(signal) {
    const [{ jobs, total }, overview] = await Promise.all([
      api(`/jobs${query({ status: state.status, q: state.q, limit: PAGE, offset: state.offset })}`, { signal }),
      api("/overview?hours=1", { signal }),
    ]);
    paintChips(overview.totals);
    const seen = signatures;
    signatures = new Map(jobs.map((job) => [job.id, `${job.status}:${job.updated_at}`]));
    body.replaceChildren(...jobs.map((job) => row(job, seen.size > 0 && seen.has(job.id) && seen.get(job.id) !== signatures.get(job.id))));
    table.hidden = jobs.length === 0;
    empty.hidden = jobs.length > 0;
    empty.replaceChildren(h("strong", { text: state.q || state.status ? "Nenhum job para este filtro" : "A fila está vazia" }),
      h("p", { text: state.q || state.status ? "Ajuste a busca ou escolha outro estado." : "Os jobs aparecem aqui quando o GitHub envia webhooks de PR." }));
    summary.textContent = total ? `${num(state.offset + 1)}–${num(state.offset + jobs.length)} de ${num(total)}` : "0 jobs";
    previous.disabled = state.offset === 0;
    next.disabled = state.offset + jobs.length >= total;
  }

  function filterBy(status) {
    state.status = status;
    state.offset = 0;
  }

  paintChips();
  return { load, filterBy };
}
