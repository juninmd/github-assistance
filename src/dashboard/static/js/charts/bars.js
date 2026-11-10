// Ranked horizontal bars. One series → one color for every bar (never a value ramp
// on nominal categories); optional segments stack with a 2px surface gap.
import { h, nextFrame, reconcile, setStyles } from "../dom.js";
import { num } from "../format.js";
import { bindTooltip } from "../tooltip.js";

export function createBars({ segments = null, color = "var(--accent)", emptyText, unit = "jobs" }) {
  const root = h("div", { class: "bars" });
  const parts = segments ?? [{ key: "value", label: unit, color }];
  const data = new Map();

  function createRow(row) {
    const node = h("div", { class: "bar-row", tabindex: "0" },
      h("span", { class: "bar-label" }),
      h("span", { class: "bar-track" }, parts.map((part) => h("span", { class: "bar-fill", style: { "--swatch": part.color, width: "0%" } }))),
      h("span", { class: "bar-value" }));
    bindTooltip(node, () => {
      const current = data.get(node.dataset.key);
      return {
        title: current.label,
        rows: parts.map((part) => ({ label: part.label, value: num(current[part.key]), color: part.color })),
        total: segments ? num(current.value) : null,
      };
    });
    data.set(String(row.label), row);
    return node;
  }

  async function update(rows) {
    if (!rows.length) {
      data.clear();
      root.replaceChildren(h("p", { class: "empty", text: emptyText }));
      return;
    }
    root.querySelector(".empty")?.remove();
    const max = Math.max(...rows.map((row) => row.value), 1);
    const created = [];
    reconcile(root, rows, (row) => row.label, (row) => {
      const node = createRow(row);
      created.push(node);
      return node;
    }, (node, row) => {
      data.set(String(row.label), row);
      node.children[0].textContent = row.label;
      node.children[0].title = row.label;
      node.children[2].textContent = num(row.value);
      node.setAttribute("aria-label", `${row.label}: ${parts.map((part) => `${num(row[part.key])} ${part.label.toLowerCase()}`).join(", ")}`);
    });
    if (created.length) await nextFrame();
    rows.forEach((row, index) => {
      const fills = [...root.children[index].children[1].children];
      let last = null;
      fills.forEach((fill, p) => {
        const value = row[parts[p].key] ?? 0;
        setStyles(fill, { width: `${(value / max) * 100}%` });
        fill.toggleAttribute("data-empty", value === 0);
        fill.classList.remove("end");
        if (value > 0) last = fill;
      });
      last?.classList.add("end");
    });
  }

  return { root, update };
}
