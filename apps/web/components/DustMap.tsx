"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Receptor, Site, Station, Status } from "@/lib/queries";
import { dayHour } from "@/lib/format";

export interface MapHour {
  ts: string;
  wind: { speed: number; dir: number; blh: number } | null;
  plumes: { site_id: string; geometry: GeoJSON.Polygon; max_conc: number }[];
  status: Record<string, Status>;
}

if (typeof window !== "undefined") maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const STATUS_COLOR: Record<Status, string> = { go: "#6CC59A", caution: "#E0A245", avoid: "#EB6E5B" };
const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

export default function DustMap({ center, sites, receptors, stations, hours }: {
  center: [number, number];
  sites: Site[];
  receptors: Receptor[];
  stations: Station[];
  hours: MapHour[];
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const h = hours[i];

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      center,
      zoom: 13.3,
      attributionControl: { compact: true },
      // OpenFreeMap: free OSM vector tiles, no API key (CARTO's basemaps started requiring one in 2026).
      style: "https://tiles.openfreemap.org/styles/dark",
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("plumes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "plume-fill", type: "fill", source: "plumes", paint: { "fill-color": "#E0A245", "fill-opacity": ["interpolate", ["linear"], ["get", "max_conc"], 50, 0.18, 500, 0.4] } });
      m.addLayer({ id: "plume-line", type: "line", source: "plumes", paint: { "line-color": "#E0A245", "line-width": 1, "line-opacity": 0.6 } });

      m.addSource("receptors", {
        type: "geojson",
        data: { type: "FeatureCollection", features: receptors.map((r) => ({ type: "Feature", properties: { name: r.name, kind: r.kind }, geometry: { type: "Point", coordinates: [r.lon, r.lat] } })) },
      });
      m.addLayer({ id: "receptors", type: "circle", source: "receptors", paint: { "circle-radius": 5, "circle-color": "#F2F2F2", "circle-stroke-color": "#0B0B0C", "circle-stroke-width": 2 } });
      m.addLayer({ id: "receptor-labels", type: "symbol", source: "receptors", minzoom: 14, layout: { "text-field": ["get", "name"], "text-size": 11, "text-offset": [0, 1.2], "text-anchor": "top", "text-optional": true, "text-font": ["Noto Sans Regular"] }, paint: { "text-color": "#A3A3A8", "text-halo-color": "#0B0B0C", "text-halo-width": 1.5 } });

      m.addSource("stations", {
        type: "geojson",
        data: { type: "FeatureCollection", features: stations.map((s) => ({ type: "Feature", properties: { name: s.name }, geometry: { type: "Point", coordinates: [s.lon, s.lat] } })) },
      });
      m.addLayer({ id: "stations", type: "circle", source: "stations", paint: { "circle-radius": 6, "circle-color": "#86BDB9", "circle-stroke-color": "#0B0B0C", "circle-stroke-width": 2 } });

      m.addSource("sites", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "sites", type: "circle", source: "sites", paint: { "circle-radius": 11, "circle-color": ["get", "color"], "circle-stroke-color": "#0B0B0C", "circle-stroke-width": 3 } });
      m.addLayer({ id: "site-labels", type: "symbol", source: "sites", layout: { "text-field": ["get", "id"], "text-size": 12, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true }, paint: { "text-color": "#0B0B0C" } });
      setReady(true);
    });
    map.current = m;
    return () => m.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !h) return;
    (m.getSource("plumes") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: h.plumes.map((p) => ({ type: "Feature", properties: { site_id: p.site_id, max_conc: p.max_conc }, geometry: p.geometry })),
    });
    (m.getSource("sites") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: sites.map((s) => ({
        type: "Feature",
        properties: { id: s.id, color: STATUS_COLOR[h.status[s.id] ?? "go"] },
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      })),
    });
  }, [ready, h, sites]);

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setI((x) => (x + 1 < hours.length ? x + 1 : (setPlaying(false), x))), 650);
    return () => clearInterval(t);
  }, [playing, hours.length]);

  const counts = useMemo(() => {
    const c = { go: 0, caution: 0, avoid: 0 };
    if (h) Object.values(h.status).forEach((s) => (c[s] += 1));
    return c;
  }, [h]);

  if (!hours.length) return <div className="empty">No forecast hours in this run.</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 18px 8px", flexWrap: "wrap" }}>
        <button className="btn" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause" : "Play the next 48 hours"}>
          {playing ? "Pause" : "Play"}
        </button>
        <span className="tab" style={{ font: "400 22px/1 var(--f-ui)", minWidth: 120 }}>{dayHour(h.ts)}</span>
        <input type="range" min={0} max={hours.length - 1} value={i} onChange={(e) => setI(Number(e.target.value))}
          aria-label="Forecast hour" style={{ flex: 1, minWidth: 160, accentColor: "#E0A245" }} />
      </div>
      <div ref={el} style={{ height: 470, margin: "0 12px", borderRadius: 14, overflow: "hidden", border: "1px solid var(--line)" }} />
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", padding: "10px 18px 16px", fontSize: 12.5, color: "var(--text-2)" }}>
        <span>{h.wind ? `Wind ${h.wind.speed.toFixed(1)} m/s from ${COMPASS[Math.round((h.wind.dir % 360) / 22.5) % 16]} · mixing layer ${Math.round(h.wind.blh)} m` : "No weather for this hour"}</span>
        <span style={{ marginLeft: "auto" }}><i className="dot" style={{ background: STATUS_COLOR.avoid }} /> Avoid {counts.avoid}</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.caution }} /> Caution {counts.caution}</span>
        <span><i className="dot" style={{ background: STATUS_COLOR.go }} /> Go {counts.go}</span>
        <span><i className="dot" style={{ background: "#F2F2F2" }} /> School, hospital, housing</span>
        <span><i className="dot" style={{ background: "#86BDB9" }} /> Station</span>
        <span><i className="dot" style={{ background: "#E0A245", opacity: 0.4 }} /> Plume above 25 µg/m³ added</span>
      </div>
    </div>
  );
}
