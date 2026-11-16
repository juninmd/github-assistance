// One shared tooltip. It enhances, never gates: every value it shows is also in a
// legend, a direct label or the chart's table view, and focus shows what hover shows.
import { h, setStyles } from "./dom.js";

const box = document.getElementById("tooltip");
const GAP = 12;

function render({ title, rows = [], total }) {
  const list = h("dl", null, rows.flatMap((row) => [
    h("span", { class: "key", style: row.color ? { "--swatch": row.color } : null }),
    h("dt", null, h("span", { text: row.label })),
    h("dd", { text: row.value }),
  ]));
  if (total != null) list.append(h("div", { class: "total" }, h("span", { text: "Total" }), h("strong", { text: total })));
  box.replaceChildren(h("h4", { text: title }), list);
}

function place(x, y) {
  box.hidden = false;
  const { width, height } = box.getBoundingClientRect();
  const left = x + GAP + width > innerWidth ? x - GAP - width : x + GAP;
  const top = Math.min(Math.max(8, y - height / 2), innerHeight - height - 8);
  setStyles(box, { translate: `${Math.max(8, left)}px ${top}px` });
}

export function hideTooltip() {
  box.hidden = true;
}

/** `describe()` is read at show time, so refreshed data needs no rebinding. */
export function bindTooltip(el, describe) {
  el.addEventListener("pointermove", (event) => {
    render(describe());
    place(event.clientX, event.clientY);
  });
  el.addEventListener("pointerleave", hideTooltip);
  el.addEventListener("focus", () => {
    const rect = el.getBoundingClientRect();
    render(describe());
    place(rect.right, rect.top + rect.height / 2);
  });
  el.addEventListener("blur", hideTooltip);
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideTooltip();
});
document.addEventListener("scroll", hideTooltip, { passive: true, capture: true });
