// Tiny DOM helpers. Text always goes through textContent/append, never innerHTML:
// job keys, repo names and errors are untrusted data.
const SVG_NS = "http://www.w3.org/2000/svg";

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "style") setStyles(el, value);
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat().filter((child) => child != null && child !== false));
  return el;
}

export function setStyles(el, styles) {
  for (const [property, value] of Object.entries(styles)) el.style.setProperty(property, value);
}

export function svg(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

export function icon(name, extraClass = "") {
  const el = svg("svg", { class: `icon ${extraClass}`.trim(), "aria-hidden": "true" });
  el.append(svg("use", { href: `#i-${name}` }));
  return el;
}

/** Keyed list update: reuses nodes so CSS transitions survive a data refresh. */
export function reconcile(parent, items, keyOf, create, update) {
  const existing = new Map([...parent.children].map((node) => [node.dataset.key, node]));
  const next = items.map((item, index) => {
    const key = String(keyOf(item));
    const node = existing.get(key) ?? create(item, index);
    node.dataset.key = key;
    existing.delete(key);
    update(node, item, index);
    return node;
  });
  for (const stale of existing.values()) stale.remove();
  next.forEach((node, index) => {
    if (parent.children[index] !== node) parent.insertBefore(node, parent.children[index] ?? null);
  });
}

export const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
