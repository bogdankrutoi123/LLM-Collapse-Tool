export function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function toPercentChange(base: number | null, delta: number | null): number | null {
  if (base === null || delta === null || base === 0) {
    return null;
  }
  return (delta / base) * 100;
}

export function isSignificantChange(percentChange: number | null, delta: number | null): boolean {
  return (percentChange !== null && Math.abs(percentChange) >= 10) || (delta !== null && Math.abs(delta) >= 0.1);
}

export function formatMetric(value: number | null, digits = 4): string {
  if (value === null) {
    return "N/A";
  }
  return value.toFixed(digits);
}

export function prettyMetricName(metric: string): string {
  return metric
    .replace(/^avg_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
