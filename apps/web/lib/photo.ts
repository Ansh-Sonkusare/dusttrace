// Residents' photos (PRD F2). The page shrinks a photo before upload; the server checks the bytes really
// are a JPEG and drops every metadata segment (EXIF with its GPS, XMP, IPTC, comments), whatever sent it.
// Pure, so it's unit-tested.

import type { Parsed } from "./officer";

export const PHOTO_MAX_BYTES = 1_000_000;
export const PHOTO_SIDE = 1280;       // longest side the page shrinks to
const MAX_SIDE = 4096;                // anything larger did not come from the page

export function fitWithin(width: number, height: number, side = PHOTO_SIDE): { width: number; height: number } {
  const k = Math.min(1, side / Math.max(width, height));
  return { width: Math.round(width * k), height: Math.round(height * k) };
}

export interface Jpeg { bytes: Uint8Array; width: number; height: number }

// APP0 (JFIF) and APP14 (Adobe colour transform) are needed to decode; every other APPn and COM is metadata.
const isMetadata = (m: number) => (m >= 0xe1 && m <= 0xef && m !== 0xee) || m === 0xfe;
const isFrame = (m: number) => m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc;

export function cleanJpeg(input: Uint8Array, max = PHOTO_MAX_BYTES): Parsed<Jpeg> {
  if (input.length > max) return { ok: false, error: "too_big" };
  const bad = { ok: false as const, error: "not_jpeg" };
  if (input.length < 4 || input[0] !== 0xff || input[1] !== 0xd8) return bad;
  const out: Uint8Array[] = [input.subarray(0, 2)];
  let i = 2, width = 0, height = 0, scans = 0;
  while (i < input.length) {
    if (input[i] !== 0xff) return bad;
    while (input[i + 1] === 0xff) i++;                      // fill bytes
    const m = input[i + 1];
    if (m === undefined) return bad;
    if (m === 0xd9) {                                        // end of image: anything after it is dropped
      if (!width || !scans) return bad;
      out.push(input.subarray(i, i + 2));
      const bytes = new Uint8Array(out.reduce((n, b) => n + b.length, 0));
      let at = 0;
      for (const b of out) { bytes.set(b, at); at += b.length; }
      return { ok: true, value: { bytes, width, height } };
    }
    if (i + 4 > input.length) return bad;
    const end = i + 2 + ((input[i + 2] << 8) | input[i + 3]);
    if (end > input.length || end < i + 4) return bad;
    if (isFrame(m)) {
      if (end < i + 9) return bad;
      height = (input[i + 5] << 8) | input[i + 6];
      width = (input[i + 7] << 8) | input[i + 8];
      if (!width || !height || Math.max(width, height) > MAX_SIDE) return bad;
    }
    if (!isMetadata(m)) out.push(input.subarray(i, end));
    i = end;
    if (m === 0xda) {                                        // a scan: copy its coded data up to the next marker
      if (!width) return bad;
      scans++;
      let j = i;
      while (j + 1 < input.length && !(input[j] === 0xff && input[j + 1] !== 0x00 && (input[j + 1] < 0xd0 || input[j + 1] > 0xd7))) j++;
      if (j + 1 >= input.length) return bad;
      out.push(input.subarray(i, j));
      i = j;
    }
  }
  return bad;
}
