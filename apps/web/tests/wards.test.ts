import { describe, expect, it } from "vitest";
import { DEFAULT_WARD, WARDS, pickWard } from "../lib/wards";

describe("ward switcher", () => {
  it("knows both pilot wards", () => {
    expect(WARDS.map((w) => w.id)).toEqual(["K-East", "P-North"]);
    expect(DEFAULT_WARD).toBe("K-East");
  });

  it("takes the query first, then the cookie, then the default; ignores unknown wards", () => {
    expect(pickWard("P-North", "K-East")).toBe("P-North");
    expect(pickWard(null, "P-North")).toBe("P-North");
    expect(pickWard(null, null)).toBe("K-East");
    expect(pickWard("Q-Nowhere", "P-North")).toBe("P-North");
    expect(pickWard("'; drop table runs; --", null)).toBe("K-East");
    expect(pickWard(null, null, "P-North")).toBe("P-North");  // env default
  });
});
