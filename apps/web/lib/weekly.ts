// Weekly ward report (PRD F5, issue #37): aggregation helpers. Pure, so they're unit-tested.

const IST_MS = 5.5 * 3600 * 1000;
const istDay = (ts: string) => new Date(new Date(ts).getTime() + IST_MS).toISOString().slice(0, 10);

export type DayResult = "hit" | "missed" | "false_alarm" | "quiet" | "no_data";
export interface SpikeDay { day: string; forecast: boolean; observed: boolean; result: DayResult }

// A day (IST) is a forecast spike day when any hour had P(PM10 > 100) >= 0.6, and an observed one
// when the ward's hourly mean went above 100 µg/m³.
export function spikeDays(fc: { ts: string; p: number }[], obs: { ts: string; pm10: number }[],
                          threshold = 100, pCut = 0.6): SpikeDay[] {
  const f = new Map<string, boolean>();
  const o = new Map<string, boolean>();
  for (const x of fc) f.set(istDay(x.ts), (f.get(istDay(x.ts)) ?? false) || x.p >= pCut);
  for (const x of obs) o.set(istDay(x.ts), (o.get(istDay(x.ts)) ?? false) || x.pm10 > threshold);
  return [...new Set([...f.keys(), ...o.keys()])].sort().map((day) => {
    const forecast = f.get(day) ?? false;
    const observed = o.get(day) ?? false;
    const result: DayResult = !o.has(day) ? "no_data" : forecast && observed ? "hit" : observed ? "missed" : forecast ? "false_alarm" : "quiet";
    return { day, forecast, observed, result };
  });
}

export function countBy<T extends Record<string, unknown>>(rows: T[], key: keyof T): [string, number][] {
  const m = new Map<string, number>();
  for (const r of rows) m.set(String(r[key]), (m.get(String(r[key])) ?? 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
