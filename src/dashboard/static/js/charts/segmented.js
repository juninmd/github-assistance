// Tall segmented bar: one whole split into parts (part-to-whole at a glance).
// Each block prints its amount only when it fits; the legend carries the names.
import { h, icon, setStyles } from "../dom.js";
import { num, percent } from "../format.js";
import { bindTooltip } from "../tooltip.js";

const CHAR_WIDTH = 8;
const PADDING = 18;

export function createSegmented(parts, onSelect) {
  const bar = h("div", { class: "segbar", role: "group", "aria-label": "Jobs por estado" });
  const legend = h("ul", { class: "legend" });
  const root = h("div", { class: "grid" }, bar, legend);
  let values = {};

  const blocks = parts.map((part) => {
    const block = h("button", { class: "seg", type: "button", style: { "--swatch": part.color, "--on": part.on, "flex-grow": "0", "flex-basis": "0" } }, h("span"));
    block.addEventListener("click", () => onSelect(part.key));
    bindTooltip(block, () => {
      const total = Object.values(values).reduce((sum, value) => sum + value, 0);
      return {
        title: part.label,
        rows: [
          { label: "Jobs", value: num(values[part.key] ?? 0), color: part.color },
          { label: "Participação", value: percent(total ? (values[part.key] ?? 0) / total : 0) },
        ],
      };
    });
    return block;
  });
  bar.append(...blocks);

  function update(nextValues) {
    values = nextValues;
    const total = parts.reduce((sum, part) => sum + (values[part.key] ?? 0), 0);
    const width = bar.clientWidth || 320;
    parts.forEach((part, index) => {
      const value = values[part.key] ?? 0;
      const block = blocks[index];
      const text = num(value);
      setStyles(block, { "flex-grow": String(value) });
      block.toggleAttribute("data-empty", value === 0);
      block.firstChild.textContent = text;
      block.classList.toggle("tight", total > 0 && (value / total) * width < text.length * CHAR_WIDTH + PADDING);
      block.setAttribute("aria-label", `${part.label}: ${text} jobs (${percent(total ? value / total : 0)}). Ver na fila`);
    });
    legend.replaceChildren(...parts.map((part) => h("li", null,
      h("span", { class: "swatch", style: { "--swatch": part.color } }),
      icon(part.icon), part.label,
      h("span", { class: "count", text: num(values[part.key] ?? 0) }))));
  }

  return { root, update };
}
