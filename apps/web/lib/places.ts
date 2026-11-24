// Reports from places with no registered site (PRD F2): those near each other are one reported place,
// which an officer can confirm into a site. Pure, so it's unit-tested.

import { metres } from "./officer";

export const PLACE_RADIUS_M = 75;
export const PLACE_DAYS = 7;

export interface PlaceReport { id: number; lat: number; lon: number; at: string; kind: string; photo: boolean }
export interface Place { ids: number[]; lat: number; lon: number; count: number; kinds: string[]; photos: number; first_at: string; last_at: string }

// Oldest first, a report joins the nearest place whose middle is within the radius, else starts one.
// Measuring from the middle keeps a street of reports from chaining into one long place.
export function groupReports(reports: PlaceReport[], radius = PLACE_RADIUS_M): Place[] {
  const sorted = [...reports].sort((a, b) => a.at.localeCompare(b.at) || a.id - b.id);
  const groups: { lat: number; lon: number; rs: PlaceReport[] }[] = [];
  for (const r of sorted) {
    let best: (typeof groups)[number] | null = null;
    for (const g of groups) if (metres(g, r) <= radius && (!best || metres(g, r) < metres(best, r))) best = g;
    if (!best) { groups.push({ lat: r.lat, lon: r.lon, rs: [r] }); continue; }
    best.rs.push(r);
    best.lat = best.rs.reduce((s, x) => s + x.lat, 0) / best.rs.length;
    best.lon = best.rs.reduce((s, x) => s + x.lon, 0) / best.rs.length;
  }
  return groups.map((g) => ({
    ids: g.rs.map((r) => r.id).sort((a, b) => a - b), lat: g.lat, lon: g.lon, count: g.rs.length,
    kinds: [...new Set(g.rs.map((r) => r.kind))], photos: g.rs.filter((r) => r.photo).length,
    first_at: g.rs[0].at, last_at: g.rs[g.rs.length - 1].at,
  })).sort((a, b) => b.count - a.count || b.last_at.localeCompare(a.last_at));
}
