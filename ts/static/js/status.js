import { h, icon } from "./dom.js";

// Entity → label, icon and color. Color follows the entity everywhere (charts,
// badges, legends), and every badge pairs it with an icon and a label.
export const STATUS = {
  pending: { label: "Pendente", icon: "clock", color: "var(--c-pending)", on: "var(--ink)" },
  running: { label: "Em execução", icon: "play", color: "var(--c-running)", on: "#0b0b0b" },
  succeeded: { label: "Concluído", icon: "check", color: "var(--c-succeeded)", on: "#ffffff" },
  blocked: { label: "Bloqueado", icon: "block", color: "var(--c-blocked)", on: "#ffffff" },
  retrying: { label: "Nova tentativa", icon: "retry", color: "var(--c-retrying)", on: "#ffffff" },
  failed: { label: "Falhou", icon: "retry", color: "var(--c-failed)", on: "#ffffff" },
};

export const OUTCOMES = ["succeeded", "blocked", "retrying"];
export const QUEUE_STATES = ["pending", "running", "succeeded", "blocked"];

export function jobState(job) {
  return job.status === "pending" && job.attempts > 0 ? "retrying" : job.status;
}

export function statusBadge(state) {
  const meta = STATUS[state] ?? { label: state, icon: "info", color: "var(--c-pending)" };
  return h(
    "span",
    { class: "badge" },
    h("span", { class: "swatch", style: { "--swatch": meta.color } }),
    icon(meta.icon),
    meta.label,
  );
}

/** Legend rows: a status key, or a custom `{ label, color }` entry. */
export function legend(entries, counts) {
  return h("ul", { class: "legend" }, entries.map((entry) => {
    const meta = typeof entry === "string" ? STATUS[entry] : entry;
    return h(
      "li",
      null,
      h("span", { class: "swatch", style: { "--swatch": meta.color } }),
      meta.icon ? icon(meta.icon) : null,
      meta.label,
      counts ? h("span", { class: "count", text: counts[entry] }) : null,
    );
  }));
}
