import { describe, expect, it } from "vitest";
import { hashIp, LIMITS, parseReport, rateLimit } from "../lib/report";

const form = (o: Record<string, string>) => {
  const f = new FormData();
  Object.entries(o).forEach(([k, v]) => f.set(k, v));
  return f;
};

describe("citizen report form", () => {
  it("accepts a known kind for a site and trims the note", () => {
    expect(parseReport(form({ site_id: "A", kind: "uncovered_truck", note: "  no tarp  " })))
      .toEqual({ ok: true, value: { site_id: "A", kind: "uncovered_truck", note: "no tarp" } });
  });

  it("rejects unknown kinds and bad site ids", () => {
    expect(parseReport(form({ site_id: "A", kind: "spam" })).ok).toBe(false);
    expect(parseReport(form({ site_id: "A; drop table", kind: "other" })).ok).toBe(false);
  });

  it("caps notes at 500 characters", () => {
    const r = parseReport(form({ site_id: "A", kind: "other", note: "y".repeat(900) }));
    expect(r.ok && r.value.note.length).toBe(500);
  });

  it("drops the bot honeypot", () => {
    expect(parseReport(form({ site_id: "A", kind: "other", website: "http://spam" })).ok).toBe(false);
  });
});

describe("rate limit", () => {
  it("allows a few reports, then stops the same device", () => {
    expect(rateLimit({ lastHour: 0, sameSiteToday: 0 })).toBe("ok");
    expect(rateLimit({ lastHour: LIMITS.perHour, sameSiteToday: 0 })).toBe("too_many");
    expect(rateLimit({ lastHour: 1, sameSiteToday: LIMITS.perSitePerDay })).toBe("too_many");
  });

  it("hashes the address with a salt and never returns it", () => {
    const h = hashIp("203.0.113.9", "salt");
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    expect(h).not.toContain("203");
    expect(hashIp("203.0.113.9", "other")).not.toBe(h);
  });
});
