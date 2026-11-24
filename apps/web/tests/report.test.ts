import { describe, expect, it } from "vitest";
import { hashIp, LIMITS, parseReport, parseReview, rateLimit, REPORT_ERROR, reportPage } from "../lib/report";

const form = (o: Record<string, string>) => {
  const f = new FormData();
  Object.entries(o).forEach(([k, v]) => f.set(k, v));
  return f;
};

describe("citizen report form", () => {
  it("accepts a known kind for a site and trims the note", () => {
    expect(parseReport(form({ site_id: "A", kind: "uncovered_truck", note: "  no tarp  " })))
      .toEqual({ ok: true, value: { site_id: "A", kind: "uncovered_truck", note: "no tarp", lat: null, lon: null, accuracy_m: null } });
  });

  it("keeps the position a resident chose to share", () => {
    const r = parseReport(form({ site_id: "A", kind: "other", lat: "19.11234567", lon: "72.8701", accuracy: "14.6" }));
    expect(r).toEqual({ ok: true, value: { site_id: "A", kind: "other", note: "", lat: 19.11234567, lon: 72.8701, accuracy_m: 15 } });
  });

  it("takes a report with no site only with a position", () => {
    expect(parseReport(form({ kind: "dry_excavation", lat: "19.1", lon: "72.87" })))
      .toEqual({ ok: true, value: { site_id: null, kind: "dry_excavation", note: "", lat: 19.1, lon: 72.87, accuracy_m: null } });
    expect(parseReport(form({ kind: "dry_excavation" }))).toEqual({ ok: false, error: "no_place" });
    expect(parseReport(form({ kind: "dry_excavation", lat: "19.1" }))).toEqual({ ok: false, error: "no_place" });
  });

  it("refuses positions that are not on the map", () => {
    expect(parseReport(form({ kind: "other", lat: "91", lon: "72.87" })).ok).toBe(false);
    expect(parseReport(form({ kind: "other", lat: "19.1", lon: "abc" })).ok).toBe(false);
    expect(parseReport(form({ site_id: "A", kind: "other", lat: "19.1", lon: "Infinity" })).ok).toBe(false);
  });

  it("rejects unknown kinds and bad site ids", () => {
    expect(parseReport(form({ site_id: "A", kind: "spam" })).ok).toBe(false);
    expect(parseReport(form({ site_id: "A; drop table", kind: "other" })).ok).toBe(false);
  });

  it("caps notes at 500 characters", () => {
    const r = parseReport(form({ site_id: "A", kind: "other", note: "y".repeat(900) }));
    expect(r.ok && r.value.note.length).toBe(500);
  });

  it("says plainly what is wrong with the old messages kept", () => {
    expect(parseReport(form({ site_id: "A", kind: "spam" }))).toEqual({ ok: false, error: "invalid" });
    expect(REPORT_ERROR.invalid).toBe("Please pick what you saw.");
    expect(REPORT_ERROR.too_many).toBe("You have sent several reports already. Please try again later.");
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

describe("officer review", () => {
  it("accepts verify and reject for a whole-number report id", () => {
    expect(parseReview(form({ id: "42", verdict: "verified" }))).toEqual({ ok: true, value: { id: 42, verdict: "verified" } });
    expect(parseReview(form({ id: "42", verdict: "rejected" })).ok).toBe(true);
  });

  it("refuses anything else", () => {
    expect(parseReview(form({ id: "42", verdict: "new" })).ok).toBe(false);
    expect(parseReview(form({ id: "4.2", verdict: "verified" })).ok).toBe(false);
    expect(parseReview(form({ verdict: "verified" })).ok).toBe(false);
  });
});

describe("a form posted without JavaScript", () => {
  it("goes back to the page it came from", () => {
    expect(reportPage("http://localhost:3131/s/osm-way-1?x=1", null)).toBe("/s/osm-way-1");
    expect(reportPage("https://dusttrace.example/report-dust?r=sent", null)).toBe("/report-dust");
    expect(reportPage(null, "A")).toBe("/s/A");
    expect(reportPage(null, null)).toBe("/report-dust");
  });

  it("never goes anywhere else", () => {
    expect(reportPage("https://evil.example/phish", null)).toBe("/report-dust");
    expect(reportPage("http://localhost/sites/A", "B")).toBe("/s/B");
    expect(reportPage("not a url", null)).toBe("/report-dust");
    expect(reportPage("http://localhost/s/..%2Fsites", null)).toBe("/report-dust");
  });
});
