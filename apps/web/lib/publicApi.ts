// Public read API (PRD F5, issue #37) for MPCB and researchers: forecast, Safe-Work Windows and Dust
// Scores. Shapes are explicit so nothing personal or internal leaks: no receptor names, people counts,
// officer notes or citizen reports. Pure, so they're unit-tested.

import { lastHour, persistenceWins, weatherNote } from "./forecastDays";

export const API_LIMIT = 120; // requests per hour per address
export const apiRateLimit = (lastHour: number): "ok" | "too_many" => (lastHour >= API_LIMIT ? "too_many" : "ok");

const r1 = (x: number) => Math.round(x * 10) / 10;

interface RunLike {
  id: number; issued_at: string; data_mode: string; model: string;
  metrics: { newest_real_reading?: string | null; filled?: { stations: number; hours: number }; forecast_hours?: number; weather_hours?: number };
}

export function publicForecast(run: RunLike, points: { ts: string; pm10: number; pm10_lo: number; pm10_hi: number; p_exceed: number }[], ward: string,
                               days: { station_id: string; day: number; starts_at: string; ends_at: string; p_exceed: number }[] = [],
                               bt?: { train_end: string; test_end: string; origins: number; data_mode: string;
                                      metrics: Parameters<typeof persistenceWins>[0]; daily?: Parameters<typeof persistenceWins>[1] } | null) {
  const last = points[points.length - 1]?.ts;
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
    // Hours after issued_at with a weather forecast; the PM10 forecast stops there. Null for runs before it was recorded.
    weather_hours: run.metrics.weather_hours ?? null,
    note: weatherNote(run.metrics.weather_hours, run.metrics.forecast_hours ?? 72),
    hours: points.map((p) => ({ ts: p.ts, pm10: r1(p.pm10), pm10_lo: r1(p.pm10_lo), pm10_hi: r1(p.pm10_hi), p_exceed_100: Math.round(p.p_exceed * 100) / 100 })),
    // P(24 h mean PM10 > 100) for the ward, for the 24 h starting at `from`. `to` is the day's last forecast hour,
    // earlier than 24 h on when the weather forecast stops first (see `note`).
    daily_24h_mean: days.filter((d) => d.station_id === "ward").sort((a, b) => a.day - b.day)
      .map((d) => ({ day: d.day, from: d.starts_at, to: lastHour(d, last), p_exceed_100: Math.round(d.p_exceed * 100) / 100 })),
    // The latest back-test, and every score on which persistence (the last value carried forward) beat the model.
    backtest: bt ? { from: bt.train_end, to: bt.test_end, forecasts: bt.origins, data_mode: bt.data_mode,
                     persistence_better: persistenceWins(bt.metrics, bt.daily) } : null,
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
