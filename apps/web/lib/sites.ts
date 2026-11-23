// Where a site came from and what DustTrace knows about its monitor. Pure, so it's unit-tested.

import type { Parsed } from "./officer";

const SOURCES: Record<string, string> = { osm: "OpenStreetMap", satellite: "Satellite, confirmed", citizen: "Residents, confirmed" };

export function sourceLabel(s: { demo: boolean; source?: string | null }): string | null {
  if (s.demo) return "Demo";
  return SOURCES[s.source ?? ""] ?? null;
}

const MONITOR: Record<string, string> = {
  not_connected: "Monitor feed not connected",
  none: "No monitor",
  trusted: "Monitor trusted",
  untrusted: "Monitor not trusted",
};

export const monitorLabel = (status: string) => MONITOR[status] ?? "Monitor status unknown";

export type Verdict = "confirmed" | "rejected";

export function parseCandidateVerdict(form: FormData): Parsed<{ id: number; verdict: Verdict }> {
  const raw = String(form.get("id") ?? "");
  const id = Number(raw);
  const verdict = String(form.get("verdict") ?? "");
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(id)) return { ok: false, error: "Unknown candidate." };
  if (verdict !== "confirmed" && verdict !== "rejected") return { ok: false, error: "Confirm or reject." };
  return { ok: true, value: { id, verdict } };
}

// A confirmed patch of new bare ground becomes a real site. Most fresh clearings are excavation;
// an officer can correct the activity later.
export function candidateSite(c: { id: number; lat: number; lon: number; area_m2: number }) {
  return {
    id: `sat-${c.id}`,
    name: `Construction site (satellite, ${c.lat.toFixed(4)}, ${c.lon.toFixed(4)})`,
    activity: "excavation",
    lat: c.lat,
    lon: c.lon,
    area_m2: Math.round(c.area_m2),
  };
}

export function parsePlaceVerdict(form: FormData): Parsed<{ ids: number[]; verdict: Verdict }> {
  const raw = String(form.get("ids") ?? "").split(",");
  const ids = raw.map(Number).sort((a, b) => a - b);
  const verdict = String(form.get("verdict") ?? "");
  if (!raw.every((x) => /^\d+$/.test(x)) || !ids.every(Number.isSafeInteger)) return { ok: false, error: "Unknown place." };
  if (verdict !== "confirmed" && verdict !== "rejected") return { ok: false, error: "Confirm or reject." };
  return { ok: true, value: { ids, verdict } };
}

// A place residents reported, once an officer confirms it, becomes a real site at the middle of its
// reports. Its size isn't known, so it keeps the default planning area; an officer can correct both.
export function placeSite(reports: { id: number; lat: number; lon: number }[]) {
  const mean = (k: "lat" | "lon") => Math.round((reports.reduce((s, r) => s + r[k], 0) / reports.length) * 1e6) / 1e6;
  const lat = mean("lat"), lon = mean("lon");
  return {
    id: `rep-${Math.min(...reports.map((r) => r.id))}`,
    name: `Construction site (reported by residents, ${lat.toFixed(4)}, ${lon.toFixed(4)})`,
    activity: "excavation",
    lat,
    lon,
  };
}

// Demo sites have one-letter codes worth showing; real sites (osm-…, sat-…) go by their name.
export const siteLabel = (id: string, name: string) => (id.length <= 3 ? `${id} · ${name}` : name);
export const mapCode = (id: string) => (id.length <= 3 ? id : "");
