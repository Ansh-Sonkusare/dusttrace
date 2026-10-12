import { describe, expect, it } from "vitest";
import { ageWord, camsSummary, sceneDate, splitPercents } from "../lib/datacheck";

describe("data check", () => {
  it("rounds the real/filled/synthetic split so it always adds up to 100", () => {
    expect(splitPercents({ hours: 168, real: 0.333, filled: 0.333, synthetic: 0.334 })).toEqual({ real: 33, filled: 33, synthetic: 34 });
    expect(splitPercents({ hours: 168, real: 0.295, filled: 0.705, synthetic: 0 })).toEqual({ real: 29, filled: 71, synthetic: 0 });
    expect(splitPercents({ hours: 0, real: 0, filled: 0, synthetic: 0 })).toBeNull();
  });

  it("says how old a station's newest reading is", () => {
    expect(ageWord(null)).toBe("No PM10 reading");
    expect(ageWord(0)).toBe("This hour");
    expect(ageWord(3)).toBe("3 hours ago");
    expect(ageWord(1)).toBe("1 hour ago");
    expect(ageWord(110)).toBe("4 days ago");
  });

  it("summarises the CAMS fill error across stations", () => {
    const s = camsSummary({
      a: { hours: 720, mae: 12, bias: -3, r: 0.6 },
      b: { hours: 700, mae: 20, bias: 5, r: 0.4 },
      c: { hours: 710, mae: 14, bias: 1, r: 0.7 },
    });
    expect(s).toEqual({ stations: 3, medianMae: 14, worst: { id: "b", mae: 20 } });
    expect(camsSummary({})).toBeNull();
  });

  it("reads a Sentinel-2 scene id as a date", () => {
    expect(sceneDate("S2B_42QZG_20260210_0_L2A")).toBe("10 Feb 2026");
    expect(sceneDate("odd")).toBe("odd");
  });
});
