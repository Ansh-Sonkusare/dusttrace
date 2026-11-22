import { createHash, timingSafeEqual } from "node:crypto";
import type { Parsed } from "./officer";

// Hygroscopic growth correction, Crilley et al. 2018, Atmos. Meas. Tech. 11:709, Eq. 5:
// C = 1 + (kappa / 1.65) / (1 / a_w - 1), with 1.65 the particle-to-water density ratio and
// kappa = 0.3 the paper's value for a site with no co-located reference. The paper fits only below
// 95% RH, where the humidity sensor's own error stays small.
export const KAPPA = 0.3;
const DENSITY_RATIO = 1.65;
export const MAX_RH = 95;
export const MAX_BATCH = 60;
const MAX_AGE_MS = 48 * 3600_000;
const MAX_AHEAD_MS = 5 * 60_000;
const MAX_PM = 2000;

export function rhCorrect(pmRaw: number, rh: number | null, kappa = KAPPA): number | null {
  if (rh === null) return pmRaw;
  if (rh > MAX_RH) return null;
  return pmRaw / (1 + (kappa / DENSITY_RATIO) * (rh / (100 - rh)));
}

export const hashKey = (key: string) => createHash("sha256").update(key).digest("hex");

export function keyMatches(key: string, hash: string): boolean {
  const a = Buffer.from(hashKey(key), "hex");
  const b = Buffer.from(/^[0-9a-f]{64}$/.test(hash) ? hash : "", "hex");
  return key.length > 0 && a.length === b.length && timingSafeEqual(a, b);
}

export interface NodeReading {
  ts: Date; pm25Raw: number; pm10Raw: number; temp: number | null; rh: number | null;
  pm25: number | null; pm10: number | null;
}

const num = (v: unknown, lo: number, hi: number): number | null | "bad" =>
  v === undefined || v === null ? null : typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi ? v : "bad";

export function parseNodePost(body: unknown, now: Date): Parsed<{ nodeId: string; readings: NodeReading[] }> {
  if (!body || typeof body !== "object") return { ok: false, error: "Send JSON." };
  const b = body as { node_id?: unknown; readings?: unknown };
  const nodeId = typeof b.node_id === "string" ? b.node_id : "";
  if (!/^node-[a-z0-9-]{1,48}$/.test(nodeId)) return { ok: false, error: "Unknown node." };
  if (!Array.isArray(b.readings) || b.readings.length === 0 || b.readings.length > MAX_BATCH) {
    return { ok: false, error: `Send 1 to ${MAX_BATCH} readings.` };
  }
  const out: NodeReading[] = [];
  for (const raw of b.readings) {
    const r = (raw ?? {}) as Record<string, unknown>;
    const pm25 = num(r.pm25, 0, MAX_PM), pm10 = num(r.pm10, 0, MAX_PM);
    const rh = num(r.rh, 0, 100), temp = num(r.temp, -10, 60);
    if (pm25 === null || pm10 === null || pm25 === "bad" || pm10 === "bad" || rh === "bad" || temp === "bad") {
      return { ok: false, error: "Readings need pm25 and pm10 in µg/m³; rh 0-100 and temp -10 to 60 if sent." };
    }
    if (pm25 > pm10) return { ok: false, error: "PM2.5 can't exceed PM10." };
    const t = r.ts === undefined ? now : typeof r.ts === "string" ? new Date(r.ts) : new Date(NaN);
    if (Number.isNaN(t.getTime()) || t.getTime() > now.getTime() + MAX_AHEAD_MS || t.getTime() < now.getTime() - MAX_AGE_MS) {
      return { ok: false, error: "ts must be ISO 8601, within the last 48 hours." };
    }
    t.setUTCSeconds(0, 0);
    out.push({ ts: t, pm25Raw: pm25, pm10Raw: pm10, temp, rh, pm25: rhCorrect(pm25, rh), pm10: rhCorrect(pm10, rh) });
  }
  return { ok: true, value: { nodeId, readings: out } };
}
