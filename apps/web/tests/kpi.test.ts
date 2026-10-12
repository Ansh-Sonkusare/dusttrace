import { describe, expect, it } from "vitest";
import { kpiTiles } from "../lib/kpi";

describe("ward KPI tiles", () => {
  it("turns the raw counts into four plain tiles", () => {
    const t = kpiTiles({ spike_p_tomorrow: 0.78, sites_holding: 2, untrusted: 1, decisions: 3, new_reports: 4 });
    expect(t.map((x) => x.value)).toEqual(["78%", "2", "1", "7"]);
    expect(t[0].label).toMatch(/PM10 above 100 tomorrow/);
    expect(t[3].label).toMatch(/3 decisions, 4 new reports/);
  });

  it("uses singulars and a dash when tomorrow has no forecast", () => {
    const t = kpiTiles({ spike_p_tomorrow: null, sites_holding: 1, untrusted: 0, decisions: 1, new_reports: 1 });
    expect(t[0].value).toBe("–");
    expect(t[1].label).toMatch(/^Site holding/);
    expect(t[3].label).toMatch(/1 decision, 1 new report$/);
  });
});
