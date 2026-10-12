import { describe, expect, it } from "vitest";
import { dataNotice } from "../lib/notice";

describe("data notice on the overview", () => {
  it("says nothing when the run is live", () => {
    expect(dataNotice("live", "2026-10-12T02:00:00Z", "2026-10-12T02:30:00Z")).toBeNull();
  });

  it("names the day real readings stopped when the feed lags", () => {
    const t = dataNotice("mixed", "2026-10-07T13:00:00Z", "2026-10-12T02:30:00Z")!;
    expect(t).toContain("7 Oct");
    expect(t).toContain("4 days");
    expect(t).toMatch(/sample stations/);
  });

  it("falls back to the generic notice without any real readings", () => {
    expect(dataNotice("synthetic", null, "2026-10-12T02:30:00Z")).toMatch(/synthetic/);
  });
});

describe("when stations are filled from CAMS", () => {
  it("says the real stations are used and recent hours come from the corrected model", () => {
    const t = dataNotice("filled", "2026-10-07T13:00:00Z", "2026-10-12T02:30:00Z", 8)!;
    expect(t).toContain("8 real CPCB stations");
    expect(t).toMatch(/Copernicus CAMS/);
    expect(t).not.toMatch(/sample stations/);
  });
});
