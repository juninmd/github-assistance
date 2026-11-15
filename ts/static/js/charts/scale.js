const TICKS = 4;

const STEPS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

/** Smallest axis top whose four ticks are whole, clean numbers. */
export function niceMax(value) {
  const rough = Math.max(value, 1) / TICKS;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = STEPS.map((factor) => factor * magnitude).find((value) => value >= rough && Number.isInteger(value));
  return Math.max(1, step) * TICKS;
}

export function ticks(max) {
  return Array.from({ length: TICKS + 1 }, (_, index) => (max / TICKS) * index);
}
