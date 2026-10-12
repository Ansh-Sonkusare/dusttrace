import { describe, expect, it } from "vitest";
import { mistSchedule, signSite, verifySite } from "../lib/plan";

describe("site-manager link", () => {
  it("verifies its own token and nothing else", () => {
    const t = signSite("A", "secret");
    expect(verifySite("A", t, "secret")).toBe(true);
    expect(verifySite("B", t, "secret")).toBe(false);
    expect(verifySite("A", t, "other-secret")).toBe(false);
    expect(verifySite("A", t.slice(0, -2) + "xx", "secret")).toBe(false);
    expect(verifySite("A", "", "secret")).toBe(false);
  });

  it("is URL-safe", () => {
    expect(signSite("A", "secret")).toMatch(/^[A-Za-z0-9_-]+$/);
  });
});

const h = (n: number) => new Date(Date.UTC(2026, 10, 12, n)).toISOString();
const row = (n: number, status: "go" | "caution" | "avoid") => ({ ts: h(n), status });

describe("misting schedule", () => {
  it("starts 90 minutes before each Avoid block and ends with it", () => {
    const s = mistSchedule([row(1, "go"), row(2, "avoid"), row(3, "avoid"), row(4, "go")]);
    expect(s).toEqual([{ from: new Date(Date.UTC(2026, 10, 12, 0, 30)).toISOString(), to: h(4) }]);
  });

  it("merges blocks whose misting would overlap", () => {
    const s = mistSchedule([row(2, "avoid"), row(3, "go"), row(4, "avoid"), row(8, "go"), row(9, "avoid")]);
    expect(s).toHaveLength(2);
    expect(s[0]).toEqual({ from: new Date(Date.UTC(2026, 10, 12, 0, 30)).toISOString(), to: h(5) });
    expect(s[1].to).toBe(h(10));
  });

  it("is empty when there is nothing to avoid", () => {
    expect(mistSchedule([row(1, "go"), row(2, "caution")])).toEqual([]);
  });
});
