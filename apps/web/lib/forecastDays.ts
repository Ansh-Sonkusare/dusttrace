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

export interface InputChange { mae: number; f1_hourly: number; f1_daily: number; on: boolean }
const INPUTS = [
  { key: "festival", name: "Festival calendar", untried: "not tried" },
  { key: "upwind_sites", name: "Construction sites upwind", untried: "not tried, no real construction sites mapped" },
] as const;

const signed = (v: number) => (v > 0 ? `+${v.toFixed(2)}` : v < 0 ? `−${Math.abs(v).toFixed(2)}` : "0.00");

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
    return { name, mae: c ? `${signed(c.mae)} µg/m³` : "–", f1Hourly: c ? signed(c.f1_hourly) : "–",
             f1Daily: c ? signed(c.f1_daily) : "–", inRuns: used, verdict };
  });
}
