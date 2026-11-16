const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
export const reducedMotion = () => reduced.matches;

/** Animate a number from its current value; the final text is always exact. */
export function countUp(el, target, format, durationMs = 700) {
  const from = Number(el.dataset.value ?? 0);
  el.dataset.value = String(target);
  cancelAnimationFrame(el.countFrame);
  if (reducedMotion() || from === target || document.hidden) {
    el.textContent = format(target);
    return;
  }
  const started = performance.now();
  const tick = (time) => {
    const progress = Math.min(1, (time - started) / durationMs);
    const eased = 1 - (1 - progress) ** 4;
    el.textContent = format(from + (target - from) * eased);
    if (progress < 1) el.countFrame = requestAnimationFrame(tick);
    else el.textContent = format(target);
  };
  el.countFrame = requestAnimationFrame(tick);
}

/** Run a DOM change inside a view transition when the browser supports it. */
export function transition(change) {
  if (!document.startViewTransition || reducedMotion()) {
    change();
    return;
  }
  document.startViewTransition(change);
}
