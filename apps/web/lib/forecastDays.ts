// The PRD F3 forecast (issue #55): P(24 h mean PM10 > 100) for the three days after a run's issue time,
// and the trial of the forecast's new inputs. Pure, so they're unit-tested.
import { dayHour } from "./format";

export interface DayRow { station_id: string; day: number; starts_at: string; ends_at: string; p_exceed: number }

const LABEL = ["Next 24 h", "24 to 48 h", "48 to 72 h"];
const pct = (p: number) => `${Math.round(p * 100)}%`;

// The first and last forecast hour of the day, in IST.
export const dayHours = (d: DayRow) => `${dayHour(d.starts_at)} to ${dayHour(d.ends_at)}`;

export function wardDays(rows: DayRow[]) {
  return rows.filter((r) => r.station_id === "ward").sort((a, b) => a.day - b.day)
    .map((d) => ({ day: d.day, label: LABEL[d.day - 1], chance: pct(d.p_exceed), hours: dayHours(d) }));
}

export function stationDays(rows: DayRow[]): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const r of rows) {
    if (r.station_id === "ward") continue;
    const days = out.get(r.station_id) ?? ["–", "–", "–"];
    days[r.day - 1] = pct(r.p_exceed);
    out.set(r.station_id, days);
  }
  return out;
}

// The engine gives no PM10 forecast for an hour without a weather forecast, and no daily chance for a day
// with under 18 of its 24 hours of weather (day d needs weather to hour 24d - 6).
export function weatherNote(weatherHours: number | undefined, forecastHours: number): string | null {
  if (weatherHours === undefined || weatherHours >= forecastHours) return null;
  const lost = [1, 2, 3].filter((d) => weatherHours < 24 * d - 6);
  const days = lost.length === 0 ? "" : lost.length === 1
    ? ` Day ${lost[0]} has under 18 hours of weather, so it has no daily chance.`
    : ` Days ${lost.slice(0, -1).join(", ")} and ${lost[lost.length - 1]} have under 18 hours of weather, so they have no daily chance.`;
  return `The forecast stops at hour ${weatherHours} because the weather forecast does.${days}`;
}

type DayScore = { f1_model: number | null; f1_persistence: number | null };
const and = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

// One plain sentence when persistence (the last 24 h mean carried forward) beat the model's ward calls.
export function persistenceNote(ward: Record<string, DayScore> | undefined): string | null {
  const worse = Object.entries(ward ?? {}).filter(([, d]) => d.f1_model != null && d.f1_persistence != null && d.f1_model < d.f1_persistence)
    .sort(([a], [b]) => Number(a) - Number(b));
  if (!worse.length) return null;
  const f = (v: number | null) => (v ?? 0).toFixed(2);
  return `Persistence called the ward's days above 100 better than the model on ${worse.length === 1 ? "day" : "days"} ${and(worse.map(([k]) => k))}`
    + ` (F1 ${and(worse.map(([, d]) => f(d.f1_persistence)))}, against ${and(worse.map(([, d]) => f(d.f1_model)))}).`;
}

export interface InputChange { mae: number; f1_hourly: number; f1_daily: number; on: boolean }
const INPUTS = [
  { key: "festival", name: "Festival calendar", untried: "not tried" },
  { key: "upwind_sites", name: "Construction sites upwind", untried: "not tried, no real construction sites mapped" },
] as const;

const signed = (v: number, d: number) => {
  const digits = v !== 0 && Math.abs(v) < 0.5 * 10 ** -d ? d + 1 : d;  // never round a real change to zero
  return v > 0 ? `+${v.toFixed(digits)}` : v < 0 ? `−${Math.abs(v).toFixed(digits)}` : (0).toFixed(d);
};

// Each new input's change on the latest trial, and whether runs use it. Only a trial on real data
// (data mode "live") can switch an input on; the engine decides, this only words it.
export function inputTrials(change: Partial<Record<string, InputChange>>, inRuns: { festival?: boolean; upwind_sites?: boolean } | undefined,
                            dataMode = "live") {
  return INPUTS.map(({ key, name, untried }) => {
    const c = change[key];
    const used = Boolean(inRuns?.[key]);
    const verdict = !c ? `Off: ${untried}`
      : dataMode === "synthetic" ? "Off: tried on synthetic data only, which can't switch it on"
      : dataMode !== "live" ? "Off: tried with partly synthetic weather, which can't switch it on"
      : !c.on ? "Off: it made the real back-test worse"
      : used ? "On: no worse on the real back-test" : "On from the next run: no worse on the real back-test";
    return { name, mae: c ? `${signed(c.mae, 2)} µg/m³` : "–", f1Hourly: c ? signed(c.f1_hourly, 3) : "–",
             f1Daily: c ? signed(c.f1_daily, 3) : "–", inRuns: used, verdict };
  });
}
