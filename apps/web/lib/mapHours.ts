import type { PlumeRow, WindowRow, WxRow } from "./queries";
import type { MapHour } from "@/components/DustMap";

/** Group plumes, windows and weather by forecast hour for the map's time slider. */
export function buildMapHours(windows: WindowRow[], plumes: PlumeRow[], wx: WxRow[]): MapHour[] {
  const byTs = new Map<string, MapHour>();
  for (const w of windows) {
    let h = byTs.get(w.ts);
    if (!h) { h = { ts: w.ts, wind: null, plumes: [], status: {} }; byTs.set(w.ts, h); }
    h.status[w.site_id] = w.status;
  }
  for (const p of plumes) {
    const h = byTs.get(p.ts);
    if (h && p.geojson) h.plumes.push({ site_id: p.site_id, geometry: JSON.parse(p.geojson), max_conc: p.max_conc });
  }
  for (const x of wx) {
    const h = byTs.get(x.ts);
    if (h) h.wind = { speed: x.wind_speed, dir: x.wind_dir, blh: x.blh };
  }
  return [...byTs.values()].sort((a, b) => a.ts.localeCompare(b.ts));
}

/** Collapse consecutive hours with the same status into spans. */
export function spans(rows: WindowRow[]) {
  const out: { status: WindowRow["status"]; from: string; to: string; rows: WindowRow[] }[] = [];
  for (const r of rows) {
    const last = out[out.length - 1];
    if (last && last.status === r.status && new Date(r.ts).getTime() - new Date(last.to).getTime() <= 3600_000) {
      last.to = r.ts; last.rows.push(r);
    } else out.push({ status: r.status, from: r.ts, to: r.ts, rows: [r] });
  }
  return out;
}
