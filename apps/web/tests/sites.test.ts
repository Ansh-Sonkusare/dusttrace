import { describe, expect, it } from "vitest";
import { candidateSite, mapCode, parseCandidateVerdict, siteLabel, sourceLabel, monitorLabel } from "../lib/sites";

const form = (o: Record<string, string>) => {
  const f = new FormData();
  Object.entries(o).forEach(([k, v]) => f.set(k, v));
  return f;
};

describe("where a site came from", () => {
  it("labels demo, OpenStreetMap and satellite sites", () => {
    expect(sourceLabel({ demo: true, source: "seed" })).toBe("Demo");
    expect(sourceLabel({ demo: false, source: "osm" })).toBe("OpenStreetMap");
    expect(sourceLabel({ demo: false, source: "satellite" })).toBe("Satellite, confirmed");
    expect(sourceLabel({ demo: false, source: "seed" })).toBeNull();
  });

  it("says an unconnected monitor feed is unknown, not missing", () => {
    expect(monitorLabel("not_connected")).toBe("Monitor feed not connected");
    expect(monitorLabel("none")).toBe("No monitor");
  });
});

describe("satellite candidate verdicts", () => {
  it("accepts confirm and reject with a whole-number id", () => {
    expect(parseCandidateVerdict(form({ id: "12", verdict: "confirmed" }))).toEqual({ ok: true, value: { id: 12, verdict: "confirmed" } });
    expect(parseCandidateVerdict(form({ id: "12", verdict: "rejected" })).ok).toBe(true);
  });

  it("refuses anything else", () => {
    expect(parseCandidateVerdict(form({ id: "1.5", verdict: "confirmed" })).ok).toBe(false);
    expect(parseCandidateVerdict(form({ id: "3", verdict: "maybe" })).ok).toBe(false);
    expect(parseCandidateVerdict(form({ verdict: "confirmed" })).ok).toBe(false);
  });

  it("turns a confirmed candidate into a real site", () => {
    const s = candidateSite({ id: 7, lat: 19.1123, lon: 72.8701, area_m2: 12345.6 });
    expect(s).toEqual({ id: "sat-7", name: "Construction site (satellite, 19.1123, 72.8701)", activity: "excavation",
      lat: 19.1123, lon: 72.8701, area_m2: 12346 });
  });
});

describe("site labels", () => {
  it("shows the code for demo sites and the name for real ones", () => {
    expect(siteLabel("A", "Metro Line 7A excavation")).toBe("A · Metro Line 7A excavation");
    expect(siteLabel("osm-way-554967617", "Metro Casting Yard")).toBe("Metro Casting Yard");
    expect(mapCode("B")).toBe("B");
    expect(mapCode("osm-way-554967617")).toBe("");
    expect(mapCode("sat-12")).toBe("");
  });
});
