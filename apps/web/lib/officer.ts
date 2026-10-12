// Officer app helpers: visiting order and the outcome form. Pure, so they're unit-tested.

export interface Point { lat: number; lon: number }

const metres = (a: Point, b: Point) => {
  const dy = (a.lat - b.lat) * 111_320;
  const dx = (a.lon - b.lon) * 111_320 * Math.cos((a.lat * Math.PI) / 180);
  return Math.hypot(dx, dy);
};

// Nearest-neighbour route from the ward office: good enough for a handful of sites a day.
export function routeOrder<T extends Point>(start: Point, sites: T[]): T[] {
  const left = [...sites];
  const out: T[] = [];
  let at = start;
  while (left.length) {
    let best = 0;
    for (let i = 1; i < left.length; i++) if (metres(at, left[i]) < metres(at, left[best])) best = i;
    at = left[best];
    out.push(...left.splice(best, 1));
  }
  return out;
}

export const OUTCOMES = {
  violation: "Violation confirmed",
  compliant: "Compliant",
  closed: "Site closed or no work",
  no_access: "Could not get in",
} as const;
export type Outcome = keyof typeof OUTCOMES;

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

export function parseOutcome(form: FormData): Parsed<{ site_id: string; outcome: Outcome; note: string }> {
  const site_id = String(form.get("site_id") ?? "").trim();
  const outcome = String(form.get("outcome") ?? "");
  const note = String(form.get("note") ?? "").trim().slice(0, 1000);
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(site_id)) return { ok: false, error: "Pick a site." };
  if (!(outcome in OUTCOMES)) return { ok: false, error: "Pick an outcome." };
  return { ok: true, value: { site_id, outcome: outcome as Outcome, note } };
}
