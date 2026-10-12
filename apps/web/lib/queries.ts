import { q, WARD } from "./db";

export type Status = "go" | "caution" | "avoid";

export interface Run {
  id: number;
  issued_at: string;
  created_at: string;
  data_mode: "live" | "synthetic" | "mixed";
  model: string;
  metrics: {
    mae_model?: number;
    mae_persistence?: number;
    f1_exceed_model?: number;
    f1_exceed_persistence?: number;
    coverage_10_90?: number;
    holdout_rows?: number;
    train_rows?: number;
    stations?: string[];
    audit?: { n: number; precision: number; recall: number; detected?: Record<string, number> };
  };
}

export interface Ward { id: string; name: string; center_lat: number; center_lon: number; bbox: number[] }
export interface FcPoint { ts: string; pm10: number; pm10_lo: number; pm10_hi: number; p_exceed: number }
export interface ObsPoint { ts: string; pm10: number }
export interface Site { id: string; name: string; activity: string; developer: string | null; lat: number; lon: number; sensor_status: string; demo: boolean; area_m2: number }
export interface Receptor { id: string; name: string; kind: "school" | "hospital" | "housing"; lat: number; lon: number; population: number; source: string }
export interface Station { id: string; name: string; source: string; lat: number; lon: number }
export type TrustBand = "trusted" | "check" | "untrusted";
export interface Audit {
  site_id: string; sensor_id: string; score: number; band: TrustBand; reasons: string[];
  vendor: string | null; has_relay: boolean; simulated: boolean; injected_fault: string | null;
}
export interface WindowRow { site_id: string; ts: string; status: Status; exposed_people: number; sensitive_hit: boolean; reason: string }
export interface PlumeRow { site_id: string; ts: string; geojson: string | null; max_conc: number }
export interface WxRow { ts: string; wind_speed: number; wind_dir: number; blh: number }

const iso = (d: unknown) => new Date(d as string).toISOString();

export async function getWard(): Promise<Ward | null> {
  const r = await q<Ward>("select id, name, center_lat, center_lon, bbox from wards where id=$1", [WARD]);
  return r[0] ?? null;
}

export async function getLatestRun(): Promise<Run | null> {
  const r = await q<Run>("select * from latest_run where ward_id=$1", [WARD]);
  if (!r[0]) return null;
  return { ...r[0], id: Number(r[0].id), issued_at: iso(r[0].issued_at), created_at: iso(r[0].created_at) };
}

export async function getWardForecast(runId: number): Promise<FcPoint[]> {
  const r = await q<FcPoint>(
    "select ts, pm10, pm10_lo, pm10_hi, p_exceed from forecasts where run_id=$1 and station_id='ward' order by ts",
    [runId],
  );
  return r.map((p) => ({ ...p, ts: iso(p.ts) }));
}

export async function getStationPeaks(runId: number) {
  return q<{ station_id: string; name: string; peak: number; peak_ts: string; hours_over: number }>(
    `select f.station_id, coalesce(s.name, f.station_id) as name,
            max(f.pm10) as peak,
            (array_agg(f.ts order by f.pm10 desc))[1] as peak_ts,
            count(*) filter (where f.p_exceed >= 0.5)::int as hours_over
       from forecasts f left join stations s on s.id = f.station_id
      where f.run_id=$1 and f.station_id <> 'ward'
      group by f.station_id, s.name order by peak desc`,
    [runId],
  );
}

// `stationIds` are the stations the run used (run.metrics.stations), so the observed line matches the forecast.
export async function getObserved(issuedAt: string, stationIds: string[] | undefined, hours = 48): Promise<ObsPoint[]> {
  const r = await q<ObsPoint>(
    `select date_trunc('hour', r.ts) as ts, avg(r.pm10)::real as pm10
       from readings r join stations s on s.id = r.station_id
      where s.ward_id=$1 and r.ts > $2::timestamptz - make_interval(hours => $3) and r.ts <= $2::timestamptz
        and r.pm10 is not null and ($4::text[] is null or r.station_id = any($4))
      group by 1 order by 1`,
    [WARD, issuedAt, hours, stationIds ?? null],
  );
  return r.map((p) => ({ ...p, ts: iso(p.ts) }));
}

export async function getSites(): Promise<Site[]> {
  return q<Site>("select id, name, activity, developer, lat, lon, sensor_status, demo, area_m2 from sites where ward_id=$1 order by id", [WARD]);
}

export async function getSite(id: string): Promise<Site | null> {
  const r = await q<Site>("select id, name, activity, developer, lat, lon, sensor_status, demo, area_m2 from sites where id=$1", [id]);
  return r[0] ?? null;
}

// Same rule as the engine (db.RECEPTORS_SQL): real OSM schools and hospitals replace the demo ones once loaded.
export async function getReceptors(): Promise<Receptor[]> {
  return q<Receptor>(
    `select id, name, kind, lat, lon, population, source from receptors r
      where ward_id=$1 and not (source = 'seed' and kind in ('school', 'hospital') and exists (
        select 1 from receptors o where o.ward_id = r.ward_id and o.source = 'osm'))`,
    [WARD],
  );
}

export async function getStations(ids?: string[]): Promise<Station[]> {
  return q<Station>(
    "select id, name, source, lat, lon from stations where ward_id=$1 and ($2::text[] is null or id = any($2))",
    [WARD, ids ?? null],
  );
}

export async function getWindows(runId: number, siteId?: string): Promise<WindowRow[]> {
  const r = await q<WindowRow>(
    `select site_id, ts, status, exposed_people, sensitive_hit, reason from safe_windows
      where run_id=$1 and ($2::text is null or site_id=$2) order by site_id, ts`,
    [runId, siteId ?? null],
  );
  return r.map((w) => ({ ...w, ts: iso(w.ts) }));
}

export async function getPlumes(runId: number): Promise<PlumeRow[]> {
  const r = await q<PlumeRow>(
    "select site_id, ts, st_asgeojson(geom, 6) as geojson, max_conc from plumes where run_id=$1 order by ts",
    [runId],
  );
  return r.map((p) => ({ ...p, ts: iso(p.ts) }));
}

export async function getWeather(fromTs: string, hours = 48): Promise<WxRow[]> {
  const r = await q<WxRow>(
    `select ts, wind_speed, wind_dir, blh from weather_hourly
      where ward_id=$1 and ts > $2::timestamptz and ts <= $2::timestamptz + make_interval(hours => $3) order by ts`,
    [WARD, fromTs, hours],
  );
  return r.map((w) => ({ ...w, ts: iso(w.ts) }));
}

export async function getSiteExposures(runId: number, siteId: string) {
  return q<{ receptor_id: string; name: string; kind: string; hours: number; peak: number }>(
    `select e.receptor_id, r.name, r.kind, count(*)::int as hours, max(e.conc) as peak
       from exposures e join receptors r on r.id = e.receptor_id
      where e.run_id=$1 and e.site_id=$2 group by 1,2,3 order by peak desc`,
    [runId, siteId],
  );
}

// Sensor trust (F1) from the run's audit, one row per site that has a sensor.
export async function getAudits(runId: number, siteId?: string): Promise<Audit[]> {
  return q<Audit>(
    `select a.site_id, a.sensor_id, a.score, a.band, a.reasons, n.vendor, n.has_relay, n.simulated, n.injected_fault
       from sensor_audits a join site_sensors n on n.id = a.sensor_id
      where a.run_id=$1 and ($2::text is null or a.site_id=$2) order by a.site_id`,
    [runId, siteId ?? null],
  );
}

export interface RankRow {
  site_id: string; name: string; rank: number; score: number; reasons: string[];
  components: { upwind: number; trust: number; reports: number; unsensored: number; violations: number };
  demo: boolean; lat: number; lon: number;
}

// The ranked "Inspect today" list (F4) for a run.
export async function getRanking(runId: number): Promise<RankRow[]> {
  return q<RankRow>(
    `select r.site_id, s.name, r.rank, r.score, r.reasons, r.components, s.demo, s.lat, s.lon
       from inspection_rank r join sites s on s.id = r.site_id where r.run_id=$1 order by r.rank`,
    [runId],
  );
}
