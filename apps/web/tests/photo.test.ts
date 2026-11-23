import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { cleanJpeg, fitWithin, PHOTO_MAX_BYTES } from "../lib/photo";

const fixture = (name: string) => new Uint8Array(readFileSync(new URL(`./fixtures/${name}`, import.meta.url)));
const has = (bytes: Uint8Array, text: string) => Buffer.from(bytes).includes(Buffer.from(text, "latin1"));

describe("photo check", () => {
  it("accepts a real JPEG and drops its EXIF, GPS and comment", () => {
    const raw = fixture("exif.jpg");
    expect(has(raw, "Exif") && has(raw, "PhoneMaker") && has(raw, "taken by a resident")).toBe(true);
    const r = cleanJpeg(raw);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.width).toBe(64);
    expect(r.value.height).toBe(48);
    expect(has(r.value.bytes, "Exif") || has(r.value.bytes, "PhoneMaker") || has(r.value.bytes, "taken by a resident")).toBe(false);
    expect([...r.value.bytes.slice(0, 2)]).toEqual([0xff, 0xd8]);
    expect([...r.value.bytes.slice(-2)]).toEqual([0xff, 0xd9]);
    expect(r.value.bytes.length).toBeLessThan(raw.length);
  });

  it("keeps every scan of a progressive JPEG", () => {
    const r = cleanJpeg(fixture("exif-progressive.jpg"));
    expect(r.ok && r.value.width === 64 && !has(r.value.bytes, "Exif")).toBe(true);
    const scans = (b: Uint8Array) => b.reduce((n, x, i) => n + (x === 0xff && b[i + 1] === 0xda ? 1 : 0), 0);
    if (r.ok) expect(scans(r.value.bytes)).toBe(scans(fixture("exif-progressive.jpg")));
  });

  it("judges by content, not by name: text, PNG and cut-off files are refused", () => {
    expect(cleanJpeg(new TextEncoder().encode("not a photo at all")).ok).toBe(false);
    expect(cleanJpeg(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0])).ok).toBe(false);
    const raw = fixture("exif.jpg");
    expect(cleanJpeg(raw.slice(0, raw.length - 40)).ok).toBe(false);
    expect(cleanJpeg(new Uint8Array([0xff, 0xd8, 0xff, 0xd9])).ok).toBe(false); // no frame, no scan
  });

  it("refuses a photo over the size cap", () => {
    const raw = fixture("exif.jpg");
    expect(cleanJpeg(raw, raw.length - 1)).toEqual({ ok: false, error: "too_big" });
    expect(PHOTO_MAX_BYTES).toBe(1_000_000);
  });

  it("refuses a frame far larger than the page ever sends", () => {
    const raw = fixture("exif.jpg");
    const big = raw.slice();
    const sof = big.findIndex((x, i) => x === 0xff && big[i + 1] === 0xc0);
    big[sof + 5] = 0x40; big[sof + 6] = 0x00; // height 16384
    expect(cleanJpeg(big).ok).toBe(false);
  });
});

describe("shrinking in the browser", () => {
  it("fits the longest side to 1280 px and never enlarges", () => {
    expect(fitWithin(4000, 3000)).toEqual({ width: 1280, height: 960 });
    expect(fitWithin(3000, 4000)).toEqual({ width: 960, height: 1280 });
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});
