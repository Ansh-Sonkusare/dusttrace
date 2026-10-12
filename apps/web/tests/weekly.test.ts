import { describe, expect, it } from "vitest";
import { countBy, spikeDays } from "../lib/weekly";

describe("weekly ward report", () => {
  it("compares forecast and observed spike days in IST", () => {
    // Forecast: P >= 0.6 on 5 Oct IST; observed ward mean above 100 on 5 and 6 Oct IST.
    const fc = [
      { ts: "2026-10-04T20:00:00Z", p: 0.7 }, // 01:30 IST 5 Oct
      { ts: "2026-10-05T20:00:00Z", p: 0.2 },
      { ts: "2026-10-06T20:00:00Z", p: 0.1 },
    ];
    const obs = [
      { ts: "2026-10-04T21:00:00Z", pm10: 130 },
      { ts: "2026-10-05T21:00:00Z", pm10: 120 },
      { ts: "2026-10-06T21:00:00Z", pm10: 60 },
    ];
    expect(spikeDays(fc, obs)).toEqual([
      { day: "2026-10-05", forecast: true, observed: true, result: "hit" },
      { day: "2026-10-06", forecast: false, observed: true, result: "missed" },
      { day: "2026-10-07", forecast: false, observed: false, result: "quiet" },
    ]);
    expect(spikeDays([{ ts: "2026-10-04T20:00:00Z", p: 0.9 }], [{ ts: "2026-10-04T21:00:00Z", pm10: 50 }])[0].result).toBe("false_alarm");
    expect(spikeDays([{ ts: "2026-10-04T20:00:00Z", p: 0.9 }], [])[0].result).toBe("no_data");
  });

  it("counts rows by a key, largest first", () => {
    expect(countBy([{ r: "D2" }, { r: "D3" }, { r: "D2" }], "r")).toEqual([["D2", 2], ["D3", 1]]);
    expect(countBy([], "r")).toEqual([]);
  });
});
