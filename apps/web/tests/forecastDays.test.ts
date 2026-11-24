import { describe, expect, it } from "vitest";
import { dayHours, inputTrials, persistenceNote, stationDays, wardDays, weatherNote } from "../lib/forecastDays";

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

describe("where the forecast stops", () => {
  it("says the forecast stops where the weather forecast does, and which days lose their chance", () => {
    expect(weatherNote(72, 72)).toBeNull();
    expect(weatherNote(undefined, 72)).toBeNull();
    expect(weatherNote(68, 72)).toBe("The forecast stops at hour 68 because the weather forecast does.");
    expect(weatherNote(60, 72)).toBe("The forecast stops at hour 60 because the weather forecast does. Day 3 has under 18 hours of weather, so it has no daily chance.");
    expect(weatherNote(40, 72)).toBe("The forecast stops at hour 40 because the weather forecast does. Days 2 and 3 have under 18 hours of weather, so they have no daily chance.");
  });
});

describe("back-test against persistence", () => {
  const day = (f1_model: number | null, f1_persistence: number | null) =>
    ({ n: 22, exceed_days: 17, hits: 17, misses: 0, false_alarms: 3, f1_model, f1_persistence, brier: 0.1 });

  it("says plainly when persistence calls the ward's days better than the model", () => {
    expect(persistenceNote({ "1": day(0.919, 0.971), "2": day(0.872, 0.914), "3": day(0.9, 0.889) }))
      .toBe("Persistence called the ward's days above 100 better than the model on days 1 and 2 (F1 0.97 and 0.91, against 0.92 and 0.87).");
    expect(persistenceNote({ "1": day(0.919, 0.971), "3": day(0.9, 0.889) }))
      .toBe("Persistence called the ward's days above 100 better than the model on day 1 (F1 0.97, against 0.92).");
    expect(persistenceNote({ "1": day(0.95, 0.9), "2": day(null, null) })).toBeNull();
    expect(persistenceNote(undefined)).toBeNull();
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
      { name: "Festival calendar", mae: "+0.12 µg/m³", f1Hourly: "−0.010", f1Daily: "0.000", inRuns: false,
        verdict: "Off: it made the real back-test worse" },
      { name: "Construction sites upwind", mae: "−0.30 µg/m³", f1Hourly: "+0.020", f1Daily: "+0.010", inRuns: true,
        verdict: "On: no worse on the real back-test" },
    ]);
  });

  it("shows a change too small for two decimals instead of hiding it", () => {
    const tiny = { festival: { mae: -0.3, f1_hourly: -0.0003, f1_daily: 0.004, on: false } };
    expect(inputTrials(tiny, { festival: false })[0]).toMatchObject({ mae: "−0.30 µg/m³", f1Hourly: "−0.0003", f1Daily: "+0.004",
      verdict: "Off: it made the real back-test worse" });
  });

  it("says when an input was never tried or the evidence isn't real data", () => {
    expect(inputTrials({ festival: change.festival }, undefined)[1]).toMatchObject({ name: "Construction sites upwind", mae: "–",
      inRuns: false, verdict: "Off: not tried, no real construction sites mapped" });
    expect(inputTrials(change, { festival: false, upwind_sites: false }, "synthetic")[1].verdict)
      .toBe("Off: tried on synthetic data only, which can't switch it on");
  });
});
