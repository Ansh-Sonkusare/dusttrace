// Public read API (PRD F5, issue #37) for MPCB and researchers: forecast, Safe-Work Windows and Dust
// Scores. Shapes are explicit so nothing personal or internal leaks: no receptor names, people counts,
// officer notes or citizen reports. Pure, so they're unit-tested.

export const API_LIMIT = 120; // requests per hour per address
export const apiRateLimit = (lastHour: number): "ok" | "too_many" => (lastHour >= API_LIMIT ? "too_many" : "ok");

const r1 = (x: number) => Math.round(x * 10) / 10;

interface RunLike {
  id: number; issued_at: string; data_mode: string; model: string;
  metrics: { newest_real_reading?: string | null; filled?: { stations: number; hours: number } };
}

export function publicForecast(run: RunLike, points: { ts: string; pm10: number; pm10_lo: number; pm10_hi: number; p_exceed: number }[], ward: string) {
  return {
    ward,
    run_id: run.id,
    issued_at: run.issued_at,
    data_mode: run.data_mode,
    newest_real_reading: run.metrics.newest_real_reading ?? null,
    filled_stations: run.metrics.filled?.stations ?? 0,
    model: run.model,
    units: "µg/m³",
    sources: ["CPCB stations via OpenAQ", "Copernicus CAMS via Open-Meteo (fills feed gaps, flagged)", "Open-Meteo weather"],
    hours: points.map((p) => ({ ts: p.ts, pm10: r1(p.pm10), pm10_lo: r1(p.pm10_lo), pm10_hi: r1(p.pm10_hi), p_exceed_100: Math.round(p.p_exceed * 100) / 100 })),
  };
}

export function publicWindows<R extends { site_id: string; ts: string; status: string }>(rows: R[],
                              sites: { id: string; name: string; demo: boolean; source?: string; lat: number; lon: number }[]) {
  const by = new Map<string, { ts: string; status: string }[]>();
  for (const r of rows) by.set(r.site_id, [...(by.get(r.site_id) ?? []), { ts: r.ts, status: r.status }]);
  return sites.filter((s) => by.has(s.id)).map((s) => ({
    site_id: s.id, name: s.name, source: s.source ?? "seed", demo: s.demo, lat: s.lat, lon: s.lon, hours: by.get(s.id)!,
  }));
}

export function publicScores<R extends { site_id: string; name: string; score: number; band: string; demo: boolean }>(rows: R[]) {
  return rows.map((r) => ({ site_id: r.site_id, name: r.name, score: Math.round(r.score), band: r.band, demo: r.demo }));
}
