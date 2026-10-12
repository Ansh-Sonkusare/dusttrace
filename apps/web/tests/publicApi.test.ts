import { describe, expect, it } from "vitest";
import { API_LIMIT, apiRateLimit, publicForecast, publicScores, publicWindows } from "../lib/publicApi";
import { isPublicPath } from "../lib/auth";

const run = { id: 11, issued_at: "2026-10-12T08:00:00.000Z", created_at: "2026-10-12T08:20:00.000Z", data_mode: "filled" as const,
  model: "lightgbm-direct-v1", metrics: { mae_model: 9, stations: ["openaq-1"], newest_real_reading: "2026-10-07T13:00:00+00:00",
  filled: { stations: 11, hours: 115 }, audit: { n: 50, precision: 1, recall: 0.9 } } };

describe("public API", () => {
  it("forecast carries the data mode and sources, not internal metrics", () => {
    const f = publicForecast(run, [{ ts: "2026-10-12T09:00:00.000Z", pm10: 80.123, pm10_lo: 60, pm10_hi: 110, p_exceed: 0.21 }], "K-East");
    expect(f.ward).toBe("K-East");
    expect(f.data_mode).toBe("filled");
    expect(f.newest_real_reading).toBe("2026-10-07T13:00:00+00:00");
    expect(f.hours[0]).toEqual({ ts: "2026-10-12T09:00:00.000Z", pm10: 80.1, pm10_lo: 60, pm10_hi: 110, p_exceed_100: 0.21 });
    expect(JSON.stringify(f)).not.toContain("audit");
    expect(f.units).toBe("µg/m³");
  });

  it("windows are per site and hour, without receptor names or people counts", () => {
    const w = publicWindows([{ site_id: "osm-way-1", ts: "2026-10-12T09:00:00.000Z", status: "avoid", exposed_people: 900, sensitive_hit: true,
      reason: "Plume reaches Marol Maternity Home" }], [{ id: "osm-way-1", name: "Metro Casting Yard", demo: false, source: "osm", lat: 19.1, lon: 72.8 }]);
    expect(w).toEqual([{ site_id: "osm-way-1", name: "Metro Casting Yard", source: "osm", demo: false, lat: 19.1, lon: 72.8,
      hours: [{ ts: "2026-10-12T09:00:00.000Z", status: "avoid" }] }]);
  });

  it("dust scores keep the score and band only", () => {
    const s = publicScores([{ site_id: "A", name: "Metro", score: 71.4, band: "fair", parts: { trust: 20 }, notes: ["x"], demo: true }]);
    expect(s).toEqual([{ site_id: "A", name: "Metro", score: 71, band: "fair", demo: true }]);
  });

  it("is rate-limited per hour and is public", () => {
    expect(apiRateLimit(API_LIMIT - 1)).toBe("ok");
    expect(apiRateLimit(API_LIMIT)).toBe("too_many");
    expect(isPublicPath("/api/public/v1/forecast")).toBe(true);
    expect(isPublicPath("/api/run")).toBe(false);
  });
});
