import { describe, expect, it } from "vitest";
import { hashKey, keyMatches, parseNodePost, rhCorrect } from "../lib/node";

const NOW = new Date("2026-11-22T10:00:00Z");
const body = (o: Record<string, unknown>) => ({ node_id: "node-marol-school", readings: [{ pm25: 40, pm10: 80, rh: 60, temp: 29 }], ...o });

describe("humidity correction (Crilley et al. 2018 Eq. 5, kappa 0.3)", () => {
  it("leaves dry air alone and shrinks readings as humidity rises", () => {
    expect(rhCorrect(100, 0)).toBe(100);
    expect(rhCorrect(100, 50)).toBeCloseTo(84.6, 1);  // 100 / (1 + (0.3 / 1.65) * 1)
    expect(rhCorrect(100, 80)).toBeCloseTo(57.9, 1);  // 100 / (1 + (0.3 / 1.65) * 4)
    expect(rhCorrect(100, null)).toBe(100);           // no RH sensor: raw, uncorrected
  });

  it("gives no value above 95% RH, beyond the range the correction was fitted on", () => {
    expect(rhCorrect(100, 96)).toBeNull();
  });
});

describe("node keys", () => {
  it("stores only a hash and compares in constant time", () => {
    const h = hashKey("k3y-0123456789abcdef");
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    expect(keyMatches("k3y-0123456789abcdef", h)).toBe(true);
    expect(keyMatches("k3y-0123456789abcdeX", h)).toBe(false);
    expect(keyMatches("", h)).toBe(false);
  });
});

describe("node post", () => {
  it("accepts a reading, stamps it to the minute and corrects it", () => {
    const p = parseNodePost(body({ readings: [{ ts: "2026-11-22T09:58:41Z", pm25: 40, pm10: 80, rh: 60, temp: 29 }] }), NOW);
    expect(p.ok).toBe(true);
    if (!p.ok) return;
    const r = p.value.readings[0];
    expect(r.ts.toISOString()).toBe("2026-11-22T09:58:00.000Z");
    expect(r.pm10).toBeCloseTo(62.86, 2);  // 80 / (1 + (0.3 / 1.65) * 1.5)
    expect(p.value.nodeId).toBe("node-marol-school");
  });

  it("uses the server's clock when the node has none", () => {
    const p = parseNodePost(body({}), NOW);
    expect(p.ok && p.value.readings[0].ts.toISOString()).toBe("2026-11-22T10:00:00.000Z");
  });

  it("refuses bad ids, bad numbers, future or stale times, and oversized batches", () => {
    const bad = [
      body({ node_id: "x; drop table" }),
      body({ readings: [] }),
      body({ readings: [{ pm25: -1, pm10: 80 }] }),
      body({ readings: [{ pm25: 40, pm10: 5000 }] }),
      body({ readings: [{ pm25: "40", pm10: 80 }] }),
      body({ readings: [{ pm25: 90, pm10: 40 }] }),             // PM2.5 can't exceed PM10
      body({ readings: [{ pm25: 40, pm10: 80, rh: 120 }] }),
      body({ readings: [{ pm25: 40, pm10: 80, ts: "2026-11-22T10:30:00Z" }] }),  // future
      body({ readings: [{ pm25: 40, pm10: 80, ts: "2026-11-19T10:00:00Z" }] }),  // older than 48 h
      body({ readings: Array.from({ length: 61 }, () => ({ pm25: 40, pm10: 80 })) }),
      null,
    ];
    for (const b of bad) expect(parseNodePost(b, NOW).ok).toBe(false);
  });
});
