import { describe, expect, it } from "vitest";
import { routeOrder, parseOutcome } from "../lib/officer";

describe("route order", () => {
  it("visits the nearest site first, then the nearest from there", () => {
    const start = { lat: 19.11, lon: 72.86 };
    const sites = [
      { id: "far", lat: 19.14, lon: 72.9 },
      { id: "near", lat: 19.111, lon: 72.861 },
      { id: "mid", lat: 19.12, lon: 72.87 },
    ];
    expect(routeOrder(start, sites).map((s) => s.id)).toEqual(["near", "mid", "far"]);
  });

  it("handles an empty list", () => {
    expect(routeOrder({ lat: 0, lon: 0 }, [])).toEqual([]);
  });
});

describe("outcome form", () => {
  const form = (o: Record<string, string>) => {
    const f = new FormData();
    Object.entries(o).forEach(([k, v]) => f.set(k, v));
    return f;
  };

  it("accepts a valid outcome and trims the note", () => {
    expect(parseOutcome(form({ site_id: "C", outcome: "violation", note: "  dry excavation, no mist  " })))
      .toEqual({ ok: true, value: { site_id: "C", outcome: "violation", note: "dry excavation, no mist" } });
  });

  it("rejects unknown outcomes and missing sites", () => {
    expect(parseOutcome(form({ site_id: "C", outcome: "bribed" })).ok).toBe(false);
    expect(parseOutcome(form({ outcome: "compliant" })).ok).toBe(false);
  });

  it("caps very long notes", () => {
    const r = parseOutcome(form({ site_id: "C", outcome: "compliant", note: "x".repeat(5000) }));
    expect(r.ok && r.value.note.length).toBe(1000);
  });
});
