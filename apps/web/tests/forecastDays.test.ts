import { describe, expect, it } from "vitest";
import { dayHours, inputTrials, persistenceSentence, persistenceWins, stationDays, wardDays, weatherNote } from "../lib/forecastDays";

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

  it("never says a day runs past the last forecast hour", () => {
    const last = new Date(Date.parse(issued) + 71 * 3600_000).toISOString(); // the weather stopped at hour 71
    expect(wardDays([block("ward", 3, 0.9)], last)[0].hours).toBe("Wed 12:30 to Thu 10:30");
    expect(wardDays([block("ward", 1, 0.9)], last)[0].hours).toBe("Mon 12:30 to Tue 11:30");
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
  const day = (f1_model: number | null, f1_persistence: number | null) => ({ f1_model, f1_persistence });
  const hours = (mae_model: number, mae_persistence: number, f1_exceed_model: number | null, f1_exceed_persistence: number | null) =>
    ({ mae_model, mae_persistence, f1_exceed_model, f1_exceed_persistence });
  // Real P-North, Sep 24 to Nov 23: persistence wins the 1-24 h error and the stations' day 1.
  const pNorth = {
    metrics: { "1-24": hours(20.87, 20.5, 0.663, 0.646), "25-48": hours(22.41, 24.48, 0.657, 0.528), "49-72": hours(23.07, 27.36, 0.675, 0.456) },
    daily: { ward: { "1": day(0.778, 0.759) }, stations: { "1": day(0.764, 0.803), "2": day(0.754, 0.74) } },
  };

  it("lists every hourly bucket and daily call where persistence beat the model", () => {
    expect(persistenceWins(pNorth.metrics, pNorth.daily)).toEqual([
      { scope: "hours 1–24", measure: "mean error, µg/m³", model: 20.9, persistence: 20.5 },
      { scope: "stations, day 1", measure: "F1, 24 h mean above 100", model: 0.76, persistence: 0.8 },
    ]);
    expect(persistenceWins({ "1-24": hours(20, 22, 0.9, 0.91) }, { ward: { "1": day(0.896, 0.899) } })).toEqual([
      { scope: "hours 1–24", measure: "F1, hours above 100", model: 0.9, persistence: 0.91 },
      { scope: "ward, day 1", measure: "F1, 24 h mean above 100", model: 0.896, persistence: 0.899 }, // a third decimal when two would tie
    ]);
    expect(persistenceWins({ "1-24": hours(20, 22, null, null) }, { ward: { "1": day(null, 0.5) } })).toEqual([]);
  });

  it("says so in one plain sentence", () => {
    expect(persistenceSentence(persistenceWins(pNorth.metrics, pNorth.daily)))
      .toBe("Persistence beat the model at hours 1–24 on mean error (20.5 against 20.9 µg/m³) and on the stations' day-1 call (F1 0.80 against 0.76).");
    expect(persistenceSentence(persistenceWins({ "1-24": hours(20, 22, 0.9, 0.91) }, { ward: { "1": day(0.896, 0.899) } })))
      .toBe("Persistence beat the model at hours 1–24 on F1 for hours above 100 (0.91 against 0.90) and on the ward's day-1 call (F1 0.899 against 0.896).");
    expect(persistenceSentence([])).toBeNull();
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
      inRuns: false, verdict: "Off: not tried, no real construction site within 3 km of a station" });
    expect(inputTrials(change, { festival: false, upwind_sites: false }, "synthetic")[1].verdict)
      .toBe("Off: tried on synthetic data only, which can't switch it on");
  });
});
