// Site-manager plan (PRD F7): a signed per-site link and the misting schedule. Pure, unit-tested.
import { createHmac, timingSafeEqual } from "node:crypto";

export function signSite(siteId: string, secret: string): string {
  return createHmac("sha256", secret).update(`plan:${siteId}`).digest("base64url").slice(0, 32);
}

export function verifySite(siteId: string, token: string, secret: string): boolean {
  const want = Buffer.from(signSite(siteId, secret));
  const got = Buffer.from(token ?? "");
  return got.length === want.length && timingSafeEqual(got, want);
}

const HOUR = 3600_000;
const LEAD = 90 * 60_000;

// Misting runs from 90 minutes before each Avoid block to its end (D2). Blocks whose misting would
// overlap or touch become one run, so the cannon isn't switched off for a few minutes in between.
export function mistSchedule(rows: { ts: string; status: string }[]): { from: string; to: string }[] {
  const avoid = rows.filter((r) => r.status === "avoid").map((r) => new Date(r.ts).getTime()).sort((a, b) => a - b);
  const out: { from: number; to: number }[] = [];
  for (const t of avoid) {
    const from = t - LEAD, to = t + HOUR;
    const last = out[out.length - 1];
    if (last && from <= last.to) last.to = Math.max(last.to, to);
    else out.push({ from, to });
  }
  return out.map((s) => ({ from: new Date(s.from).toISOString(), to: new Date(s.to).toISOString() }));
}

// The signing secret. Production needs PLAN_SECRET; without it, plan links are off.
export function planSecret(): string | null {
  return process.env.PLAN_SECRET ?? (process.env.NODE_ENV === "production" ? null : "dev-only-plan-secret");
}
