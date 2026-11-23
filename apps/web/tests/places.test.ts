import { describe, expect, it } from "vitest";
import { groupReports, PLACE_RADIUS_M, type PlaceReport } from "../lib/places";

const BASE = { lat: 19.115, lon: 72.87 };
// A report `north` and `east` metres from BASE.
const at = (id: number, north: number, east: number, hour = id, kind = "dry_excavation", photo = true): PlaceReport => ({
  id, kind, photo,
  lat: BASE.lat + north / 111_320,
  lon: BASE.lon + east / (111_320 * Math.cos((BASE.lat * Math.PI) / 180)),
  at: new Date(Date.UTC(2026, 10, 20, hour)).toISOString(),
});

describe("reported places", () => {
  it("groups two reports 40 m apart into one place", () => {
    const places = groupReports([at(1, 0, 0), at(2, 0, 40, 2, "uncovered_debris", false)]);
    expect(places).toHaveLength(1);
    expect(places[0].count).toBe(2);
    expect(places[0].ids).toEqual([1, 2]);
    expect(places[0].kinds).toEqual(["dry_excavation", "uncovered_debris"]);
    expect(places[0].photos).toBe(1);
    expect(places[0].lat).toBeCloseTo(BASE.lat, 6);
    expect(places[0].lon).toBeCloseTo(at(9, 0, 20).lon, 6); // the middle of the two
  });

  it("keeps a report 500 m away as a separate place", () => {
    const places = groupReports([at(1, 0, 0), at(2, 0, 40), at(3, 500, 0)]);
    expect(places.map((p) => p.count)).toEqual([2, 1]);
    expect(places[1].ids).toEqual([3]);
  });

  it("uses about 75 m", () => {
    expect(PLACE_RADIUS_M).toBe(75);
    expect(groupReports([at(1, 0, 0), at(2, 70, 0)])).toHaveLength(1);
    expect(groupReports([at(1, 0, 0), at(2, 80, 0)])).toHaveLength(2);
  });

  it("does not chain a street of reports into one long place", () => {
    const street = [0, 60, 120, 180, 240].map((m, i) => at(i + 1, 0, m));
    expect(groupReports(street).every((p) => p.count <= 3)).toBe(true);
  });

  it("gives the same places whatever order the reports arrive in, and puts the busiest first", () => {
    const rs = [at(1, 0, 0), at(2, 500, 0), at(3, 0, 30), at(4, 500, 20), at(5, 10, 10)];
    const a = groupReports(rs);
    expect(groupReports([...rs].reverse())).toEqual(a);
    expect(a.map((p) => p.ids)).toEqual([[1, 3, 5], [2, 4]]);
    expect(a[0].first_at < a[0].last_at).toBe(true);
  });

  it("puts a report that arrived after the page loaded into the place an officer confirms", () => {
    const onPage = groupReports([at(1, 0, 0), at(2, 0, 40)]);
    const now = groupReports([at(1, 0, 0), at(2, 0, 40), at(3, 30, 20)]);
    expect(onPage[0].ids).toEqual([1, 2]);
    expect(now.find((p) => p.ids.includes(onPage[0].ids[0]))?.ids).toEqual([1, 2, 3]);
  });
});
