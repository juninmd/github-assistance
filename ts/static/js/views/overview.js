import { createBars } from "../charts/bars.js";
import { createColumns } from "../charts/columns.js";
import { createSegmented } from "../charts/segmented.js";
import { sparkline } from "../charts/sparkline.js";
import { h, icon } from "../dom.js";
import { bucketLabel, bucketRange, compact, duration, num, percent } from "../format.js";
import { countUp } from "../motion.js";
import { OUTCOMES, QUEUE_STATES, STATUS, legend } from "../status.js";

const RANGES = [[24, "24 h"], [48, "48 h"], [168, "7 dias"]];
const OPEN = { key: "open", label: "Em aberto", color: "var(--c-pending)" };
const series = (keys) => keys.map((key) => ({ key, ...STATUS[key] }));

function card(title, subtitle, body, tools) {
  return h("article", { class: "card" },
    h("div", { class: "card-head" }, h("div", null, h("h2", { text: title }), h("p", { text: subtitle })),
      tools ? h("div", { class: "card-tools" }, tools) : null), body);
}

function tile(label) {
  const value = h("p", { class: "tile-value skeleton", text: "000" });
  const foot = h("p", { class: "tile-foot" });
  return { root: h("article", { class: "card tile" }, h("p", { class: "tile-label", text: label }), value, foot), value, foot };
}

export function createOverview(root, { onRange, onStatus }) {
  let hours = 24;
  const range = h("div", { class: "segmented", role: "group", "aria-label": "Período" },
    RANGES.map(([value, text]) => h("button", { type: "button", text, "aria-pressed": String(value === hours),
      onclick: (event) => {
        hours = value;
        for (const button of range.children) button.setAttribute("aria-pressed", String(button === event.currentTarget));
        onRange(hours);
      } })));
  const tiles = { due: tile("Fila pronta"), running: tile("Em execução"), succeeded: tile("Concluídos"), blocked: tile("Bloqueados"), rate: tile("Taxa de sucesso") };
  const columns = createColumns(series(OUTCOMES));
  const chartSlot = h("div", null, columns.root);
  const toggle = h("button", { class: "icon-button", type: "button", "aria-pressed": "false", "aria-label": "Ver como tabela", title: "Ver como tabela" }, icon("table"));
  toggle.addEventListener("click", () => {
    const asTable = toggle.getAttribute("aria-pressed") !== "true";
    toggle.setAttribute("aria-pressed", String(asTable));
    toggle.replaceChildren(icon(asTable ? "chart" : "table"));
    chartSlot.replaceChildren(asTable ? columns.table() : columns.root);
  });
  const states = createSegmented(series(QUEUE_STATES), onStatus);
  const backlog = h("dl", { class: "facts" });
  const decisions = createBars({ emptyText: "Nenhuma decisão registrada no período." });
  const repositories = createBars({ segments: [...series(["succeeded", "blocked"]), OPEN], emptyText: "Nenhum repositório ativo no período." });
  const deliveries = createBars({ emptyText: "Nenhum webhook recebido no período.", unit: "entregas", color: "var(--ink-3)" });
  const charts = [
    h("div", { class: "grid split" },
      card("Resultado dos jobs por período", "Último desfecho de cada PR, agrupado pela hora da atualização.", h("div", { class: "grid" }, legend(OUTCOMES), chartSlot), toggle),
      card("Estado da fila", "Todos os jobs persistidos. Clique num estado para abrir a fila filtrada.", h("div", { class: "grid" }, states.root, backlog))),
    h("div", { class: "grid thirds" },
      card("Decisões", "O que a política de merge decidiu.", decisions.root),
      card("Repositórios mais ativos", "Jobs atualizados no período, por desfecho.", h("div", { class: "grid" }, legend(["succeeded", "blocked", OPEN]), repositories.root)),
      card("Webhooks recebidos", "Entregas do GitHub por tipo de evento.", deliveries.root)),
  ];
  root.replaceChildren(
    h("header", { class: "view-head" }, h("div", null, h("h1", { id: "overview-title", text: "Visão geral" }),
      h("p", { text: "Fila durável de PRs: o que entrou, o que foi decidido e o que está parado." })), h("div", { class: "view-tools" }, range)),
    h("div", { class: "grid tiles" }, Object.values(tiles).map((item, index) => { item.root.style.setProperty("--order", String(index)); return item.root; })),
    ...charts);

  function setTile(item, value, format, foot) {
    item.value.classList.remove("skeleton");
    countUp(item.value, value, format);
    item.foot.replaceChildren(...foot);
  }

  function update(data) {
    root.classList.remove("is-stale");
    const { backlog: queue, window: recent, throughput, service } = data;
    const label = RANGES.find(([value]) => value === data.window_hours)?.[1] ?? `${data.window_hours} h`;
    const whole = (value) => compact(Math.round(value));
    setTile(tiles.due, queue.due, whole, [queue.due ? `mais antigo há ${duration(queue.oldest_due_age_seconds)}` : "nada aguardando"]);
    setTile(tiles.running, queue.running, whole, [h("span", { class: "pill", "data-tone": service.worker_alive ? "good" : "warning" }, icon(service.worker_alive ? "check" : "info"), service.worker_alive ? "worker ativo" : "worker parado")]);
    setTile(tiles.succeeded, recent.succeeded, whole, [`em ${label}`, sparkline(throughput.map((p) => p.succeeded), STATUS.succeeded.color)]);
    setTile(tiles.blocked, recent.blocked, whole, [`em ${label}`, sparkline(throughput.map((p) => p.blocked), STATUS.blocked.color)]);
    tiles.rate.value.classList.remove("skeleton");
    tiles.rate.value.textContent = percent(recent.success_rate);
    tiles.rate.foot.replaceChildren(h("span", { class: "meter", role: "img", "aria-label": `Taxa de sucesso ${percent(recent.success_rate)}` }, h("span", { style: { width: `${(recent.success_rate ?? 0) * 100}%` } })));
    columns.update(throughput.map((point) => ({ ...point, label: bucketLabel(point.start, data.bucket_seconds), rangeLabel: bucketRange(point.start, data.bucket_seconds) })));
    if (toggle.getAttribute("aria-pressed") === "true") chartSlot.replaceChildren(columns.table());
    states.update(Object.fromEntries(QUEUE_STATES.map((key) => [key, data.totals[key] ?? 0])));
    backlog.replaceChildren(...[["Agendados (backoff)", num(queue.scheduled)], ["Em nova tentativa", num(queue.retrying)], ["Modo", service.mode], ["Ciclo do worker", `${service.poll_interval_seconds} s`]]
      .flatMap(([term, value]) => [h("div", null, h("dt", { text: term }), h("dd", { text: value }))]));
    decisions.update(data.decisions.map((row) => ({ ...row, label: row.label || "sem decisão" })));
    repositories.update(data.repositories.map((row) => ({ ...row, label: row.label || "desconhecido" })));
    deliveries.update(data.deliveries);
  }

  return { update, hours: () => hours, stale: () => root.classList.add("is-stale") };
}
