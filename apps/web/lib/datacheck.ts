// Data check (issue #29): helpers for the Data page. Pure, so they're unit-tested.

export interface Shares { hours: number; real: number; filled: number; synthetic: number }
export interface CamsCheck { hours: number; mae: number; bias: number; r: number | null; from?: string; to?: string }

// Whole percentages that add up to 100 (largest remainder), or null when the run had no inputs.
export function splitPercents(s: Shares): { real: number; filled: number; synthetic: number } | null {
  if (!s.hours) return null;
  const keys = ["real", "filled", "synthetic"] as const;
  const raw = keys.map((k) => s[k] * 100);
  const out = raw.map(Math.floor);
  let left = 100 - out.reduce((a, b) => a + b, 0);
  const order = raw.map((v, i) => [v - Math.floor(v), i] as const).sort((a, b) => b[0] - a[0] || b[1] - a[1]);
  for (const [, i] of order) { if (left <= 0) break; out[i] += 1; left -= 1; }
  return { real: out[0], filled: out[1], synthetic: out[2] };
}

export function ageWord(h: number | null): string {
  if (h === null || h === undefined) return "No PM10 reading";
  if (h < 1) return "This hour";
  if (h < 48) return `${h} ${h === 1 ? "hour" : "hours"} ago`;
  return `${Math.floor(h / 24)} days ago`;
}

export function camsSummary(cams: Record<string, CamsCheck>): { stations: number; medianMae: number; worst: { id: string; mae: number } } | null {
  const rows = Object.entries(cams);
  if (!rows.length) return null;
  const maes = rows.map(([, c]) => c.mae).sort((a, b) => a - b);
  const mid = Math.floor(maes.length / 2);
  const median = maes.length % 2 ? maes[mid] : (maes[mid - 1] + maes[mid]) / 2;
  const [id, c] = rows.reduce((w, r) => (r[1].mae > w[1].mae ? r : w));
  return { stations: rows.length, medianMae: Math.round(median * 10) / 10, worst: { id, mae: c.mae } };
}

// "S2B_42QZG_20260210_0_L2A" -> "10 Feb 2026"
export function sceneDate(id: string): string {
  const d = id.split("_")[2];
  if (!d || !/^\d{8}$/.test(d)) return id;
  return new Date(`${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}T00:00:00Z`)
    .toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
