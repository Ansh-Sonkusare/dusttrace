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
  const b = { n: 50, precision: 1, recall: 0.8, stations: { "openaq-12024": "Chakala-Andheri East", "openaq-6956": "Powai" } };

  it("names the stations and how much of the scored week they measured", () => {
    expect(ambientNote({ ...b, ambient: { hours: 336, real: 1, filled: 0, synthetic: 0 } }))
      .toBe("Simulated sensors built from real readings at Chakala-Andheri East, Powai: all of the scored week measured.");
    expect(ambientNote({ ...b, ambient: { hours: 336, real: 0.74, filled: 0.26, synthetic: 0 } }))
      .toBe("Simulated sensors built from real readings at Chakala-Andheri East, Powai: 74% of the scored week measured; each hour a station missed comes from the next station that measured it.");
  });

  it("says so when the readings were synthetic, and stays vague for an older run", () => {
    expect(ambientNote({ ...b, ambient: { hours: 336, real: 0, filled: 0, synthetic: 1 } }))
      .toBe("Simulated sensors built from synthetic readings at Chakala-Andheri East, Powai.");
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
