// Citizen reports from the public site page (PRD F8). Pure helpers, unit-tested.
import { createHash } from "node:crypto";

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

export function parseReport(form: FormData): Parsed<{ site_id: string; kind: ReportKind; note: string }> {
  if (String(form.get("website") ?? "")) return { ok: false, error: "Rejected." }; // honeypot for bots
  const site_id = String(form.get("site_id") ?? "").trim();
  const kind = String(form.get("kind") ?? "");
  const note = String(form.get("note") ?? "").trim().slice(0, 500);
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(site_id)) return { ok: false, error: "Unknown site." };
  if (!(kind in REPORT_KINDS)) return { ok: false, error: "Pick what you saw." };
  return { ok: true, value: { site_id, kind: kind as ReportKind, note } };
}

export function rateLimit(counts: { lastHour: number; sameSiteToday: number }): "ok" | "too_many" {
  return counts.lastHour >= LIMITS.perHour || counts.sameSiteToday >= LIMITS.perSitePerDay ? "too_many" : "ok";
}

// Only a salted hash of the address is stored, and only to rate-limit.
export function hashIp(ip: string, salt: string): string {
  return createHash("sha256").update(`${salt}:${ip}`).digest("hex");
}
