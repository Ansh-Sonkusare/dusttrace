// Citizen reports (PRD F2, F8): from a site's public page, or from the page for places with no site, where
// the resident's position is required. Pure helpers, unit-tested.
import { createHash } from "node:crypto";
import { WARDS } from "./wards";

export const REPORT_KINDS = {
  uncovered_debris: "Uncovered debris or soil",
  no_barricade: "No barricade or green net",
  dry_excavation: "Digging or breaking without water",
  uncovered_truck: "Truck leaving uncovered or muddy",
  other: "Something else",
} as const;
export type ReportKind = keyof typeof REPORT_KINDS;

export const LIMITS = { perHour: 5, perSitePerDay: 3 } as const;

export type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

// What the resident is told for each refusal; the API answers with the code and this text.
export const REPORT_ERROR: Record<string, string> = {
  rejected: "This report was not accepted.",
  site: "We could not find that site.",
  invalid: "Please pick what you saw.",
  no_place: "Please share your location, so the officer can find the place.",
  place: "Your location could not be read. Please try again.",
  outside: `DustTrace covers ${WARDS.map((w) => w.name).join(" and ")} for now, and this place is outside them.`,
  too_big: "That photo is too large. Please pick another one.",
  not_jpeg: "That file is not a photo DustTrace can take. Please attach a JPEG photo.",
  too_many: "You have sent several reports already. Please try again later.",
};

export interface Report {
  site_id: string | null; kind: ReportKind; note: string;
  lat: number | null; lon: number | null; accuracy_m: number | null;
}

const num = (v: FormDataEntryValue | null) => (v === null || String(v).trim() === "" ? null : Number(v));

export function parseReport(form: FormData): Parsed<Report> {
  if (String(form.get("website") ?? "")) return { ok: false, error: "rejected" }; // honeypot for bots
  const site_id = String(form.get("site_id") ?? "").trim() || null;
  const kind = String(form.get("kind") ?? "");
  const note = String(form.get("note") ?? "").trim().slice(0, 500);
  const [lat, lon, accuracy] = [num(form.get("lat")), num(form.get("lon")), num(form.get("accuracy"))];
  if (site_id !== null && !/^[A-Za-z0-9_-]{1,40}$/.test(site_id)) return { ok: false, error: "site" };
  if (!(kind in REPORT_KINDS)) return { ok: false, error: "invalid" };
  const placed = lat !== null && lon !== null;
  if (!placed && site_id === null) return { ok: false, error: "no_place" };
  if (placed && !(Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180)) {
    return { ok: false, error: "place" };
  }
  const accuracy_m = placed && accuracy !== null && Number.isFinite(accuracy) && accuracy >= 0 ? Math.round(accuracy) : null;
  return { ok: true, value: { site_id, kind: kind as ReportKind, note, lat: placed ? lat : null, lon: placed ? lon : null, accuracy_m } };
}

export type Review = "verified" | "rejected";

// An officer verifies or rejects a resident's report from the console.
export function parseReview(form: FormData): Parsed<{ id: number; verdict: Review }> {
  const raw = String(form.get("id") ?? "");
  const id = Number(raw);
  const verdict = String(form.get("verdict") ?? "");
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(id)) return { ok: false, error: "Unknown report." };
  if (verdict !== "verified" && verdict !== "rejected") return { ok: false, error: "Verify or reject." };
  return { ok: true, value: { id, verdict } };
}

export function rateLimit(counts: { lastHour: number; sameSiteToday: number }): "ok" | "too_many" {
  return counts.lastHour >= LIMITS.perHour || counts.sameSiteToday >= LIMITS.perSitePerDay ? "too_many" : "ok";
}

// A form posted without JavaScript is sent back to its own page with ?r=<code>: the page it came from when
// that is a report page, else the site's page or /report-dust. Only these paths, so it can't redirect away.
export function reportPage(referer: string | null, siteId: string | null): string {
  let from = "";
  try { from = new URL(referer ?? "").pathname; } catch { /* no referer */ }
  if (/^\/s\/[A-Za-z0-9_-]{1,40}$/.test(from) || from === "/report-dust") return from;
  return siteId ? `/s/${encodeURIComponent(siteId)}` : "/report-dust";
}

// Only a salted hash of the address is stored, and only to rate-limit.
export function hashIp(ip: string, salt: string): string {
  return createHash("sha256").update(`${salt}:${ip}`).digest("hex");
}
