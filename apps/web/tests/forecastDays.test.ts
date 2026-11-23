import { describe, expect, it } from "vitest";
import { dayHours, inputTrials, stationDays, wardDays } from "../lib/forecastDays";

const issued = "2026-11-23T06:00:00.000Z"; // 11:30 IST
const block = (station_id: string, day: number, p: number) => ({
  station_id, day, p_exceed: p,
  starts_at: new Date(Date.parse(issued) + (24 * day - 23) * 3600_000).toISOString(),
  ends_at: new Date(Date.parse(issued) + 24 * day * 3600_000).toISOString(),
});

describe("daily exceedance (24 h mean above 100)", () => {
  it("names the IST hours each day covers", () => {
    expect(dayHours(block("ward", 1, 0.2))).toBe("Mon 12:30 to Tue 11:30");
  });

  it("gives the ward's three days in order, as percentages", () => {
    const rows = [block("ward", 3, 0.613), block("st-1", 1, 0.9), block("ward", 1, 0.04), block("ward", 2, 0.25)];
    expect(wardDays(rows).map((d) => [d.label, d.chance, d.hours])).toEqual([
      ["Next 24 h", "4%", "Mon 12:30 to Tue 11:30"],
      ["24 to 48 h", "25%", "Tue 12:30 to Wed 11:30"],
      ["48 to 72 h", "61%", "Wed 12:30 to Thu 11:30"],
    ]);
    expect(wardDays([])).toEqual([]);
  });

  it("lines up each station's three days, without the ward", () => {
    const rows = [block("st-1", 2, 0.5), block("ward", 1, 0.1), block("st-1", 1, 0.3), block("st-1", 3, 0.7), block("st-2", 1, 0.2)];
    expect(stationDays(rows)).toEqual(new Map([["st-1", ["30%", "50%", "70%"]], ["st-2", ["20%", "–", "–"]]]));
  });
});

describe("new forecast inputs on trial", () => {
  const change = {
    festival: { mae: 0.12, f1_hourly: -0.01, f1_daily: 0, on: false },
    upwind_sites: { mae: -0.3, f1_hourly: 0.02, f1_daily: 0.01, on: true },
  };

  it("shows each input's change and whether runs use it", () => {
    const rows = inputTrials(change, { festival: false, upwind_sites: true });
    expect(rows).toEqual([
      { name: "Festival calendar", mae: "+0.12 µg/m³", f1Hourly: "−0.01", f1Daily: "0.00", inRuns: false,
        verdict: "Off: it made the real back-test worse" },
      { name: "Construction sites upwind", mae: "−0.30 µg/m³", f1Hourly: "+0.02", f1Daily: "+0.01", inRuns: true,
        verdict: "On: no worse on the real back-test" },
    ]);
  });

  it("says when an input was never tried or the evidence isn't real data", () => {
    expect(inputTrials({ festival: change.festival }, undefined)[1]).toMatchObject({ name: "Construction sites upwind", mae: "–",
      inRuns: false, verdict: "Off: not tried, no real construction sites mapped" });
    expect(inputTrials(change, { festival: false, upwind_sites: false }, "synthetic")[1].verdict)
      .toBe("Off: tried on synthetic data only, which can't switch it on");
  });
});
