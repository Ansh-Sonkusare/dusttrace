import { describe, expect, it } from "vitest";
import { checkAuth, isPublicPath } from "../lib/auth";

const basic = (user: string, pass: string) => `Basic ${Buffer.from(`${user}:${pass}`).toString("base64")}`;

describe("console password", () => {
  it("asks for the password when it is missing or wrong", () => {
    expect(checkAuth("/cases", null, "s3cret", true)).toBe("challenge");
    expect(checkAuth("/cases", basic("officer", "nope"), "s3cret", true)).toBe("challenge");
  });

  it("lets the right password in, whatever the user name", () => {
    expect(checkAuth("/cases", basic("officer", "s3cret"), "s3cret", true)).toBe("ok");
    expect(checkAuth("/", basic("", "s3cret"), "s3cret", true)).toBe("ok");
  });

  it("keeps resident and site-manager pages open", () => {
    for (const p of ["/s/A", "/plan/A", "/api/report", "/_next/static/x.js", "/maplibre/worker.js", "/favicon.ico"]) {
      expect(isPublicPath(p)).toBe(true);
      expect(checkAuth(p, null, "s3cret", true)).toBe("ok");
    }
    expect(isPublicPath("/sites/A")).toBe(false);
    expect(isPublicPath("/officer")).toBe(false);
  });

  it("refuses to run unprotected in production", () => {
    expect(checkAuth("/cases", null, undefined, true)).toBe("misconfigured");
    expect(checkAuth("/s/A", null, undefined, true)).toBe("ok");
  });

  it("stays open in development when no password is set", () => {
    expect(checkAuth("/cases", null, undefined, false)).toBe("ok");
  });
});
