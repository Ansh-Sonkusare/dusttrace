// The PRD F3 forecast (issue #55): P(24 h mean PM10 > 100) for the three days after a run's issue time,
// and the trial of the forecast's new inputs. Pure, so they're unit-tested.
import { dayHour } from "./format";

export interface DayRow { station_id: string; day: number; starts_at: string; ends_at: string; p_exceed: number }

const LABEL = ["Next 24 h", "24 to 48 h", "48 to 72 h"];
const pct = (p: number) => `${Math.round(p * 100)}%`;

// The first and last forecast hour of the day, in IST.
export const dayHours = (d: DayRow) => `${dayHour(d.starts_at)} to ${dayHour(d.ends_at)}`;

// A day's last hour, but never past the last hour the run forecast (the weather forecast can stop first).
export const lastHour = (d: DayRow, last?: string) => (last && last < d.ends_at ? last : d.ends_at);

export function wardDays(rows: DayRow[], last?: string) {
  return rows.filter((r) => r.station_id === "ward").sort((a, b) => a.day - b.day)
    .map((d) => ({ day: d.day, label: LABEL[d.day - 1], chance: pct(d.p_exceed), hours: dayHours({ ...d, ends_at: lastHour(d, last) }) }));
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
type HourScore = { mae_model: number; mae_persistence: number; f1_exceed_model: number | null; f1_exceed_persistence: number | null };
export interface PersistenceWin { scope: string; measure: string; model: number; persistence: number }

const and = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
// Rounded to `d` decimals, or one more when that would make the two look equal.
const pair = (model: number, persistence: number, d: number) => {
  const k = model.toFixed(d) === persistence.toFixed(d) ? d + 1 : d;
  return { model: Number(model.toFixed(k)), persistence: Number(persistence.toFixed(k)) };
};
const MAE = "mean error, µg/m³", F1H = "F1, hours above 100", F1D = "F1, 24 h mean above 100";

// Where persistence (the last value, or the last 24 h mean, carried forward) beat the model on a back-test:
// lower error or higher exceedance F1 on an hourly bucket, or higher F1 on the ward's or stations' daily calls.
export function persistenceWins(metrics: Record<string, HourScore>,
                                daily?: { ward?: Record<string, DayScore>; stations?: Record<string, DayScore> } | null): PersistenceWin[] {
  const out: PersistenceWin[] = [];
  for (const [k, b] of Object.entries(metrics).sort(([a], [c]) => parseInt(a) - parseInt(c))) {
    const scope = `hours ${k.replace("-", "–")}`;
    if (b.mae_persistence < b.mae_model) out.push({ scope, measure: MAE, ...pair(b.mae_model, b.mae_persistence, 1) });
    if (b.f1_exceed_model != null && b.f1_exceed_persistence != null && b.f1_exceed_persistence > b.f1_exceed_model) {
      out.push({ scope, measure: F1H, ...pair(b.f1_exceed_model, b.f1_exceed_persistence, 2) });
    }
  }
  for (const level of ["ward", "stations"] as const) {
    for (const [k, d] of Object.entries(daily?.[level] ?? {}).sort(([a], [c]) => Number(a) - Number(c))) {
      if (d.f1_model != null && d.f1_persistence != null && d.f1_persistence > d.f1_model) {
        out.push({ scope: `${level}, day ${k}`, measure: F1D, ...pair(d.f1_model, d.f1_persistence, 2) });
      }
    }
  }
  return out;
}

const digits = (w: PersistenceWin) => Math.max(...[w.model, w.persistence].map((v) => (String(v).split(".")[1] ?? "").length),
                                                w.measure === MAE ? 1 : 2);
export function persistenceSentence(wins: PersistenceWin[]): string | null {
  if (!wins.length) return null;
  const parts = wins.map((w) => {
    const [p, m] = [w.persistence, w.model].map((v) => v.toFixed(digits(w)));
    if (w.measure === F1D) {
      const [level, day] = w.scope.split(", day ");
      return `on the ${level === "ward" ? "ward's" : "stations'"} day-${day} call (F1 ${p} against ${m})`;
    }
    return w.measure === MAE ? `at ${w.scope} on mean error (${p} against ${m} µg/m³)` : `at ${w.scope} on F1 for hours above 100 (${p} against ${m})`;
  });
  return `Persistence beat the model ${and(parts)}.`;
}

export interface InputChange { mae: number; f1_hourly: number; f1_daily: number; on: boolean }
const INPUTS = [
  { key: "festival", name: "Festival calendar", untried: "not tried" },
  { key: "upwind_sites", name: "Construction sites upwind", untried: "not tried, no real construction site within 3 km of a station" },
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
