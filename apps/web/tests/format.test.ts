import { describe, expect, it } from "vitest";
import { spanText } from "../lib/format";

const ist = (day: number, h: number) => new Date(Date.UTC(2026, 10, day) + (h - 5.5) * 3600_000).toISOString();

describe("a span of hours", () => {
  it("runs from its first hour to the end of its last", () => {
    expect(spanText(ist(24, 9.5), ist(24, 10.5))).toBe("Tue 09:30–11:30");
  });

  it("names the end day when the span crosses midnight", () => {
    expect(spanText(ist(24, 19.5), ist(25, 6.5))).toBe("Tue 19:30–Wed 07:30");
  });
});
