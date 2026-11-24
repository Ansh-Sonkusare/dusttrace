import { describe, expect, it } from "vitest";
import { EXPOSURE_DEFINITION, fmtExposure, moveText, planGain } from "../lib/exposure";
import type { WindowRow } from "../lib/queries";

// IST o'clock (fractions allowed) on Tue 24 Nov 2026, as a UTC ISO string.
const ist = (h: number) => new Date(Date.UTC(2026, 10, 24) + (h - 5.5) * 3600_000).toISOString();
const row = (h: number, status: WindowRow["status"], o: Partial<WindowRow> = {}): WindowRow => ({
  site_id: "A", ts: ist(h), status, exposed_people: 0, sensitive_hit: false, reason: "", person_exposure: 0,
  person_exposure_15: 0, move_to: null, avoided: 0, avoided_15: 0, ...o,
});
const span = (rows: WindowRow[]) => ({ rows });

describe("where to move the work in an Avoid span", () => {
  it("names the hours the work moves to, merged into ranges", () => {
    const s = span([row(9, "avoid", { move_to: ist(12) }), row(10, "avoid", { move_to: ist(13) }), row(11, "avoid", { move_to: ist(14) })]);
    expect(moveText(s)).toBe("Move the work to Tue 12:00–15:00.");
  });

  it("lists split ranges in time order", () => {
    const s = span([row(9, "avoid", { move_to: ist(8) }), row(10, "avoid", { move_to: ist(12) }), row(11, "avoid", { move_to: ist(13) })]);
    expect(moveText(s)).toBe("Move the work to Tue 08:00–09:00 and 12:00–14:00.");
  });

  it("names the day whenever it changes, for a span across midnight", () => {
    const wed = (h: number) => ist(h + 24);
    const s = span([row(20, "avoid", { move_to: ist(17) }), row(21, "avoid", { move_to: ist(9) }),
                    row(30, "avoid", { move_to: wed(17) })]);   // Wed 06:00
    expect(moveText(s)).toBe("Move the work to Tue 09:00–10:00 and 17:00–18:00 and Wed 17:00–18:00.");
  });

  it("covers early mornings: dusty work is allowed from 06:00", () => {
    expect(moveText(span([row(6, "avoid", { move_to: ist(15) }), row(7, "avoid", { move_to: ist(16) })])))
      .toBe("Move the work to Tue 15:00–17:00.");
  });

  it("says when only part of the work has somewhere better to go", () => {
    const s = span([row(9, "avoid", { move_to: ist(12) }), row(10, "avoid")]);
    expect(moveText(s)).toBe("Move 1 h to Tue 12:00–13:00; no better hour that day for the other 1 h.");
  });

  it("says so when there is no better hour", () => {
    expect(moveText(span([row(6, "avoid"), row(7, "avoid")]))).toBe("No better hour that day to move the work to.");
  });

  it("says there is nothing to move outside 06:00–22:00", () => {
    expect(moveText(span([row(22, "avoid"), row(23, "avoid")]))).toBe("Outside 06:00–22:00: no dusty work to move.");
    expect(moveText(span([row(21.5, "avoid")]))).toBe("Outside 06:00–22:00: no dusty work to move."); // runs to 22:30
    expect(moveText(span([row(20.5, "avoid", { move_to: ist(21) })]))).toBe("Move the work to Tue 21:00–22:00.");
  });
});

describe("what following the plan keeps off people", () => {
  it("sums the allowed hours' exposure and what the moves keep off, on both counts", () => {
    const rows = [
      row(5, "avoid", { person_exposure: 99_000, person_exposure_15: 90_000 }),        // before 06:00
      row(9, "avoid", { person_exposure: 70_000, person_exposure_15: 50_000, move_to: ist(12), avoided: 40_000,
                        avoided_15: 50_000, exposed_people: 1200 }),
      row(10, "caution", { person_exposure: 20_000, person_exposure_15: 10_000 }),
      row(12, "go", { person_exposure: 30_000 }),                                        // faint dust only
      row(14, "avoid", { person_exposure: 4_000, person_exposure_15: 3_000 }),          // no better hour that day
      row(21.5, "caution", { person_exposure: 5_000, person_exposure_15: 5_000 }),      // runs past 22:00
    ];
    expect(planGain(rows)).toEqual({
      without: 124_000, avoided: 40_000, with: 84_000, pct: (40_000 / 124_000) * 100,
      without_15: 63_000, avoided_15: 50_000, pct_15: (50_000 / 63_000) * 100, people: 1200, stuck: 1,
    });
  });

  it("has no percentage when nothing reaches anyone", () => {
    expect(planGain([row(9, "go")])).toEqual({ without: 0, avoided: 0, with: 0, pct: null, without_15: 0, avoided_15: 0,
                                               pct_15: null, people: 0, stuck: 0 });
  });
});

describe("the definition shown with the numbers", () => {
  it("says people across the ward boundary are estimated, not counted", () => {
    expect(EXPOSURE_DEFINITION).toContain("homes downwind in neighbouring wards are estimated at this ward's density, not counted");
  });
});

describe("person-exposure numbers", () => {
  it("rounds to three figures with Indian digit grouping", () => {
    expect(fmtExposure(1_234_567)).toBe("12,30,000");
    expect(fmtExposure(84_449)).toBe("84,400");
    expect(fmtExposure(845.4)).toBe("845");
    expect(fmtExposure(0)).toBe("0");
  });
});
