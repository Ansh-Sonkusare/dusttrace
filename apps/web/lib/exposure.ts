// Person-exposure avoided (PRD F7) and where each Avoid span's dusty work moves. The engine picks the hours
// (services/engine/dusttrace/exposure.py) and stores them on each window row; these helpers only read them back.
// Pure, unit-tested.
import type { WindowRow } from "./queries";
import { dayHour, hhmm } from "./format";

const HOUR = 3600_000;
// Dusty work is allowed 06:00–22:00 IST: an hour counts when it starts at 06:00 or later and ends by 22:00.
const allowed = (ts: string) => {
  const h = (((new Date(ts).getTime() / HOUR + 5.5) % 24) + 24) % 24;
  return h >= 6 && h + 1 <= 22;
};

// Where the dusty work of an Avoid span goes: "Move the work to Tue 12:00–15:00.", or why it doesn't.
export function moveText(span: { rows: WindowRow[] }): string {
  const work = span.rows.filter((r) => r.status === "avoid" && allowed(r.ts));
  if (work.length === 0) return "Outside 06:00–22:00: no dusty work to move.";
  const to = work.filter((r) => r.move_to).map((r) => new Date(r.move_to!).getTime()).sort((a, b) => a - b);
  const stuck = work.length - to.length;
  if (to.length === 0) return "No better hour that day to move the work to.";
  const ranges: { from: number; to: number }[] = [];
  for (const t of to) {
    const last = ranges[ranges.length - 1];
    if (last && t === last.to) last.to = t + HOUR;
    else ranges.push({ from: t, to: t + HOUR });
  }
  const iso = (t: number) => new Date(t).toISOString();
  const day = (t: number) => new Date(t + 5.5 * HOUR).toISOString().slice(0, 10);
  const where = ranges.map((r, i) => `${i > 0 && day(r.from) === day(ranges[i - 1].from) ? hhmm(iso(r.from)) : dayHour(iso(r.from))}–${hhmm(iso(r.to))}`).join(" and ");
  return stuck === 0 ? `Move the work to ${where}.` : `Move ${to.length} h to ${where}; no better hour that day for the other ${stuck} h.`;
}

// Over a set of window rows: person-exposure (person·µg/m³·h) without the plan and what the plan's moves keep off
// people, counting all dust and (`_15`) only receptors given 15 µg/m³ or more; the most people the moved hours would
// have put in the dust at once; and the Avoid hours with no better hour to move to.
export function planGain(rows: WindowRow[]) {
  const work = rows.filter((r) => allowed(r.ts));
  const sum = (xs: WindowRow[], f: (r: WindowRow) => number) => xs.reduce((a, r) => a + f(r), 0);
  const pct = (a: number, b: number) => (b > 0 ? (a / b) * 100 : null);
  const without = sum(work, (r) => r.person_exposure);
  const avoided = sum(rows, (r) => r.avoided);
  const without_15 = sum(work, (r) => r.person_exposure_15);
  const avoided_15 = sum(rows, (r) => r.avoided_15);
  const people = rows.filter((r) => r.move_to).reduce((a, r) => Math.max(a, r.exposed_people), 0);
  const stuck = work.filter((r) => r.status === "avoid" && !r.move_to).length;
  return { without, avoided, with: without - avoided, pct: pct(avoided, without),
           without_15, avoided_15, pct_15: pct(avoided_15, without_15), people, stuck };
}

export function fmtExposure(n: number): string {
  if (n === 0) return "0";
  const p = 10 ** Math.max(0, Math.floor(Math.log10(Math.abs(n))) - 2);
  return (Math.round(n / p) * p).toLocaleString("en-IN");
}

export const EXPOSURE_DEFINITION =
  "Person-exposure is people × the PM10 a site adds where they are (µg/m³) × hours, at every school, hospital and " +
  "home cell the plume reaches, however faint. The figure at 15 µg/m³ or more counts only the places the Safe-Work " +
  "Windows flag, and can be checked against the exposures rows. People: homes from Census 2011 spread over the ward's " +
  "mapped housing; homes downwind in neighbouring wards are estimated at this ward's density, not counted; 800 per " +
  "school and 400 per hospital, assumed. Without the plan, dusty work runs every allowed hour, " +
  "06:00–22:00 IST; with it, each Avoid hour's work moves to the cleanest Go or Caution hour that day that is lower " +
  "on both counts, and its dust there is counted. Modelled from the forecast, not measured.";
