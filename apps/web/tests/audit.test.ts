import { describe, expect, it } from "vitest";
import { ambientNote, benchmarkTable, calibrationNote } from "../lib/audit";

const rates = (p: number, r: number, d: Record<string, number>) => ({ precision: p, recall: r, detected: d });

const audit = {
  n: 50, precision: 1, recall: 0.951, detected: {},
  sensors: { none: 9, flatline: 9, dropout: 8, too_clean: 8, drift: 8, rh_bias: 8 },
  shown: { flatline: 9, dropout: 8, too_clean: 8, drift: 8, rh_bias: 0 },
  methods: {
    rules: rates(1, 0.951, { none: 0, flatline: 1, dropout: 1, too_clean: 1, drift: 0.75, rh_bias: 1 }),
    forest: rates(0.97, 0.8, { none: 0.11, flatline: 1, dropout: 0, too_clean: 1, drift: 1, rh_bias: 1 }),
    both: rates(0.976, 1, { none: 0.11, flatline: 1, dropout: 1, too_clean: 1, drift: 1, rh_bias: 1 }),
  },
};

describe("the audit benchmark table", () => {
  it("has a column per method and a row per injected fault, as whole percentages", () => {
    const t = benchmarkTable(audit)!;
    expect(t.methods.map((m) => m.label)).toEqual(["Rule checks", "Isolation Forest", "Either"]);
    const drift = t.faults.find((f) => f.fault === "drift")!;
    expect(drift).toEqual({ fault: "drift", label: "Calibration drift", sensors: 8, shown: 8, rates: ["75%", "100%", "100%"] });
    expect(t.faults.find((f) => f.fault === "rh_bias")!.shown).toBe(0);
    expect(t.faults.map((f) => f.fault)).toEqual(["flatline", "dropout", "too_clean", "drift", "rh_bias"]);
    expect(t.healthy).toEqual({ sensors: 9, rates: ["0%", "11%", "11%"] });
    expect(t.precision).toEqual(["100%", "97%", "98%"]);
    expect(t.recall).toEqual(["95%", "80%", "100%"]);
  });

  it("shows only the rule checks for a run from before the forest", () => {
    const t = benchmarkTable({ n: 50, precision: 0.9, recall: 0.85, detected: { none: 0, flatline: 1 } })!;
    expect(t.methods.map((m) => m.label)).toEqual(["Rule checks"]);
    expect(t.faults).toEqual([{ fault: "flatline", label: "Stuck readings", sensors: null, shown: null, rates: ["100%"] }]);
  });

  it("has nothing to show when the run had no ambient readings to build sensors on", () => {
    expect(benchmarkTable(undefined)).toBeNull();
    expect(benchmarkTable({ n: 0, precision: 1, recall: 1 })).toBeNull();
  });
});

describe("where the simulated sensors' air came from", () => {
  const chakala = { name: "Chakala-Andheri East", sensors: 50, hours: 168, measured: 158, next_station: 10, interpolated: 0 };

  it("says plainly that all the sensors share one station, and where its missing hours came from", () => {
    expect(ambientNote({ n: 50, precision: 1, recall: 0.8, stations: { "openaq-12024": chakala } }))
      .toBe("All 50 simulated sensors share one station, Chakala-Andheri East, which measured 158 of the scored week's 168 hours; the other 10 came from the next station that measured them.");
    expect(ambientNote({ n: 50, precision: 1, recall: 0.8, stations: { "openaq-12024": { ...chakala, measured: 168, next_station: 0 } } }))
      .toBe("All 50 simulated sensors share one station, Chakala-Andheri East, which measured all 168 hours of the scored week.");
    expect(ambientNote({ n: 50, precision: 1, recall: 0.8, stations: { "openaq-12024": { ...chakala, measured: 155, next_station: 10, interpolated: 3 } } }))
      .toBe("All 50 simulated sensors share one station, Chakala-Andheri East, which measured 155 of the scored week's 168 hours; the other 10 came from the next station that measured them; 3 that no station measured were interpolated.");
  });

  it("lists each station when the sensors are spread over several", () => {
    const stations = { a: { ...chakala, sensors: 30 }, b: { ...chakala, name: "Powai", sensors: 20, measured: 168, next_station: 0 } };
    expect(ambientNote({ n: 50, precision: 1, recall: 0.8, stations }))
      .toBe("The 50 simulated sensors are built on 2 stations: Chakala-Andheri East (30 sensors, 158 of 168 hours measured), Powai (20 sensors, 168 of 168 hours measured).");
  });

  it("says so when the readings were synthetic, and stays vague for an older run", () => {
    expect(ambientNote({ n: 50, precision: 1, recall: 1, synthetic_ambient: true, stations: { s: chakala } }))
      .toBe("All 50 simulated sensors are built from synthetic readings at Chakala-Andheri East.");
    expect(ambientNote({ n: 50, precision: 1, recall: 1 })).toBe("Simulated sensors built from station readings.");
  });
});

describe("calibration date", () => {
  it("shows the date the audit used and labels a simulated one", () => {
    expect(calibrationNote({ calibrated_on: "2026-10-05", simulated: true })).toBe("Last calibrated on 5 Oct 2026 (simulated date).");
    expect(calibrationNote({ calibrated_on: "2026-10-05", simulated: false })).toBe("Last calibrated on 5 Oct 2026.");
    expect(calibrationNote({ calibrated_on: null, simulated: false })).toBe("No calibration date on record.");
  });
});
