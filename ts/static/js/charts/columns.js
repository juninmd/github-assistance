// Stacked columns over time. Marks are HTML boxes: ≤24px wide, 2px surface gap
// between segments, 4px rounded data-end, square at the baseline.
import { h, nextFrame, setStyles } from "../dom.js";
import { compact, num } from "../format.js";
import { bindTooltip } from "../tooltip.js";
import { niceMax, ticks } from "./scale.js";

const LABEL_WIDTH = 46;

export function createColumns(series) {
  const axis = h("div", { class: "columns-axis", "aria-hidden": "true" });
  const grid = h("div", { "aria-hidden": "true" });
  const bars = h("div", { class: "columns-bars", role: "group", "aria-label": "Colunas por período; use as setas para navegar" });
  const plot = h("div", { class: "columns-plot" }, grid, bars);
  const xAxis = h("div", { class: "columns-x", "aria-hidden": "true" });
  const root = h("div", { class: "columns" }, axis, plot, xAxis);
  let points = [];

  bars.addEventListener("keydown", (event) => {
    const columns = [...bars.children];
    const index = columns.indexOf(document.activeElement);
    const target = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: columns.length - 1 }[event.key];
    if (index < 0 || target == null || !columns[target]) return;
    event.preventDefault();
    columns.forEach((column, i) => { column.tabIndex = i === target ? 0 : -1; });
    columns[target].focus();
  });

  function buildColumn(index) {
    const column = h("button", { class: "column", type: "button", tabindex: index === 0 ? "0" : "-1" },
      series.map((item) => h("span", { class: "seg", style: { "--swatch": item.color, "--i": String(index), height: "0%" } })));
    bindTooltip(column, () => {
      const point = points[index];
      return {
        title: point.rangeLabel,
        rows: series.map((item) => ({ label: item.label, value: num(point[item.key]), color: item.color })),
        total: num(series.reduce((sum, item) => sum + point[item.key], 0)),
      };
    });
    return column;
  }

  async function update(nextPoints) {
    const fresh = bars.children.length !== nextPoints.length;
    points = nextPoints;
    const top = niceMax(Math.max(...points.map((p) => series.reduce((sum, item) => sum + p[item.key], 0)), 0));
    const marks = ticks(top);
    axis.replaceChildren(...marks.map((value) => h("span", { text: compact(value), style: { bottom: `${(value / top) * 100}%` } })));
    grid.replaceChildren(...marks.slice(1).map((value) => h("span", { class: "gridline", style: { bottom: `${(value / top) * 100}%` } })));
    if (fresh) {
      bars.replaceChildren(...points.map((_, index) => buildColumn(index)));
      await nextFrame();
    }
    const every = Math.max(1, Math.ceil((points.length * LABEL_WIDTH) / Math.max(plot.clientWidth, 1)));
    xAxis.replaceChildren(...points.map((point, index) => h("span", { text: index % every === 0 ? point.label : "" })));
    points.forEach((point, index) => {
      const column = bars.children[index];
      let topSegment = null;
      series.forEach((item, s) => {
        const segment = column.children[s];
        const value = point[item.key];
        setStyles(segment, { height: `${(value / top) * 100}%` });
        segment.toggleAttribute("data-empty", value === 0);
        segment.classList.remove("top");
        if (value > 0) topSegment = segment;
      });
      topSegment?.classList.add("top");
      column.setAttribute("aria-label", `${point.rangeLabel}: ${series.map((item) => `${num(point[item.key])} ${item.label.toLowerCase()}`).join(", ")}`);
    });
  }

  function table() {
    return h("div", { class: "data-table-wrap" }, h("table", { class: "data-table" },
      h("thead", null, h("tr", null, h("th", { scope: "col", text: "Período" }), series.map((item) => h("th", { scope: "col", text: item.label })))),
      h("tbody", null, points.map((point) => h("tr", null,
        h("th", { scope: "row", text: point.rangeLabel }), series.map((item) => h("td", { text: num(point[item.key]) })))))));
  }

  return { root, update, table };
}
