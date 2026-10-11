// MapLibre resolves its worker relative to import.meta.url, which breaks under the Next bundler.
// Copy the worker into public/ and point MapLibre at it (see components/DustMap.tsx).
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/dist/maplibre-gl.css"));
mkdirSync("public/maplibre", { recursive: true });
copyFileSync(join(dist, "maplibre-gl-worker.mjs"), "public/maplibre/maplibre-gl-worker.mjs");
console.log("copied maplibre worker to public/maplibre/");
