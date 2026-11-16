import { svg } from "../dom.js";

const WIDTH = 84;
const HEIGHT = 24;
const PAD = 4;

/** Trend line in the de-emphasis ink; only the latest point wears the accent. */
export function sparkline(values, color) {
  const root = svg("svg", { class: "spark", viewBox: `0 0 ${WIDTH} ${HEIGHT}`, "aria-hidden": "true" });
  if (values.length < 2) return root;
  const max = Math.max(...values, 1);
  const x = (index) => PAD + (index / (values.length - 1)) * (WIDTH - PAD * 2);
  const y = (value) => HEIGHT - PAD - (value / max) * (HEIGHT - PAD * 2);
  const d = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
  const dot = svg("circle", { cx: x(values.length - 1), cy: y(values.at(-1)), r: 3.5 });
  dot.style.setProperty("--swatch", color);
  root.append(svg("path", { d }), dot);
  return root;
}
