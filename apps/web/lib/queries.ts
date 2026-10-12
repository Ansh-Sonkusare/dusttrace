import { q, ward } from "./db";

export type Status = "go" | "caution" | "avoid";

export interface Run {
  id: number;
  issued_at: string;
  created_at: string;
  data_mode: "live" | "synthetic" | "mixed" | "filled";
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
    newest_real_reading?: string | null;
    filled?: { stations: number; hours: number; corrections?: Record<string, { slope: number; intercept: number; mae: number; hours: number }> };
    inputs?: { hours: number; real: number; filled: number; synthetic: number };
  };
}

export interface Ward { id: string; name: string; center_lat: number; center_lon: number; bbox: number[]; boundary?: { type: "Polygon"; coordinates: number[][][] } | null }
export interface FcPoint { ts: string; pm10: number; pm10_lo: number; pm10_hi: number; p_exceed: number }
export interface ObsPoint { ts: string; pm10: number }
export interface Site { id: string; name: string; activity: string; developer: string | null; lat: number; lon: number; sensor_status: string; demo: boolean; area_m2: number; source: string; ward_id: string }
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

export async function getWard(wardId?: string): Promise<Ward | null> {
  const r = await q<Ward>("select id, name, center_lat, center_lon, bbox, boundary from wards where id=$1", [wardId ?? await ward()]);
  return r[0] ?? null;
}

// Public site pages pass the site's own ward; console pages use the ward the viewer picked.
export async function getLatestRun(wardId?: string): Promise<Run | null> {
  const r = await q<Run>("select * from latest_run where ward_id=$1", [wardId ?? await ward()]);
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
    [await ward(), issuedAt, hours, stationIds ?? null],
  );
  return r.map((p) => ({ ...p, ts: iso(p.ts) }));
}

export async function getSites(): Promise<Site[]> {
  return q<Site>("select id, name, activity, developer, lat, lon, sensor_status, demo, area_m2, source, ward_id from sites where ward_id=$1 and active order by demo, id", [await ward()]);
}

export async function getSite(id: string): Promise<Site | null> {
  const r = await q<Site>("select id, name, activity, developer, lat, lon, sensor_status, demo, area_m2, source, ward_id from sites where id=$1", [id]);
  return r[0] ?? null;
}

// Same rule as the engine (db.RECEPTORS_SQL): real OSM schools and hospitals replace the demo ones once loaded.
export async function getReceptors(): Promise<Receptor[]> {
  return q<Receptor>(
    `select id, name, kind, lat, lon, population, source from receptors r
      where ward_id=$1 and not (source = 'seed' and kind in ('school', 'hospital') and exists (
        select 1 from receptors o where o.ward_id = r.ward_id and o.source = 'osm'))`,
    [await ward()],
  );
}

export async function getStations(ids?: string[]): Promise<Station[]> {
  return q<Station>(
    "select id, name, source, lat, lon from stations where ward_id=$1 and ($2::text[] is null or id = any($2))",
    [await ward(), ids ?? null],
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
    [await ward(), fromTs, hours],
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
  demo: boolean; source: string; lat: number; lon: number;
}

// The ranked "Inspect today" list (F4) for a run.
export async function getRanking(runId: number): Promise<RankRow[]> {
  return q<RankRow>(
    `select r.site_id, s.name, r.rank, r.score, r.reasons, r.components, s.demo, s.source, s.lat, s.lon
       from inspection_rank r join sites s on s.id = r.site_id where r.run_id=$1 order by r.rank`,
    [runId],
  );
}

export interface CaseAction {
  id: number; phase: "initial" | "final"; action: string; type: string; route: "auto" | "site" | "L1" | "L2";
  rule: string; reason: string; status: string; at: string | null; deadline: string | null; decided_by: string | null;
}
export interface CaseRow {
  id: number; site_id: string; site_name: string; state: string; triggers: string[]; signals: string[];
  hypotheses: [string, number][]; what_changed: string | null; stop_reason: string | null;
  opened_at: string; updated_at: string; actions: CaseAction[];
}

// Open cases (F12) with their actions, the ones waiting on an officer first.
export async function getOpenCases(): Promise<CaseRow[]> {
  const rows = await q<CaseRow>(
    `select c.id, c.site_id, s.name as site_name, c.state, c.triggers, c.signals, c.hypotheses, c.what_changed,
            c.stop_reason, c.opened_at, c.updated_at,
            coalesce((select json_agg(a order by a.phase desc, a.id) from case_actions a where a.case_id = c.id), '[]') as actions
       from cases c join sites s on s.id = c.site_id
      where c.closed_at is null and s.ward_id=$1
      order by (select count(*) from case_actions a where a.case_id = c.id and a.status='proposed') desc, c.site_id`,
    [await ward()],
  );
  return rows.map((r) => ({ ...r, opened_at: iso(r.opened_at), updated_at: iso(r.updated_at) }));
}

export interface Inspection { id: number; site_id: string; site_name: string; outcome: string; note: string | null; officer: string | null; at: string }

export async function getRecentInspections(limit = 10): Promise<Inspection[]> {
  const r = await q<Inspection>(
    `select i.id, i.site_id, s.name as site_name, i.outcome, i.note, i.officer, i.at
       from inspections i join sites s on s.id = i.site_id where s.ward_id=$1 order by i.at desc limit $2`,
    [await ward(), limit],
  );
  return r.map((x) => ({ ...x, at: iso(x.at) }));
}

// Actions on each site's open case that wait on the ward officer (route L1).
export async function getOfficerActions(): Promise<{ site_id: string; action: string; rule: string; status: string }[]> {
  return q(
    `select c.site_id, a.action, a.rule, a.status from case_actions a join cases c on c.id = a.case_id
      where c.closed_at is null and a.phase='final' and a.route='L1' and a.status in ('proposed','approved','requested')
      order by c.site_id, a.id`,
  );
}

export interface DustScore {
  site_id: string; score: number; band: "good" | "fair" | "poor"; notes: string[];
  components: { trust: number; spikes: number; windows: number; reports: number; inspections: number };
}

export async function getDustScores(runId: number, siteId?: string): Promise<DustScore[]> {
  return q<DustScore>(
    `select site_id, score, band, components, notes from dust_scores where run_id=$1 and ($2::text is null or site_id=$2)
      order by site_id`,
    [runId, siteId ?? null],
  );
}

export async function countReports(ipHash: string, siteId: string): Promise<{ lastHour: number; sameSiteToday: number }> {
  const r = await q<{ last_hour: number; same_site: number }>(
    `select count(*) filter (where at > now() - interval '1 hour')::int as last_hour,
            count(*) filter (where site_id=$2 and at > now() - interval '1 day')::int as same_site
       from citizen_reports where ip_hash=$1 and at > now() - interval '1 day'`,
    [ipHash, siteId],
  );
  return { lastHour: r[0]?.last_hour ?? 0, sameSiteToday: r[0]?.same_site ?? 0 };
}

export async function getLastAcceptance(siteId: string): Promise<{ accepted_at: string; run_id: number | null } | null> {
  const r = await q<{ accepted_at: string; run_id: number | null }>(
    "select accepted_at, run_id from plan_acceptances where site_id=$1 order by accepted_at desc limit 1", [siteId]);
  return r[0] ? { ...r[0], accepted_at: iso(r[0].accepted_at) } : null;
}

export interface AlertRow { id: number; kind: "critical" | "action" | "receptor" | "sensor"; site_id: string | null; case_id: number | null; title: string; action: string }

export async function getAlerts(runId: number): Promise<AlertRow[]> {
  return q<AlertRow>(
    `select id, kind, site_id, case_id, title, action from alerts where run_id=$1
      order by array_position(array['critical','action','receptor','sensor'], kind), site_id`,
    [runId],
  );
}

// Raw numbers behind the overview KPI tiles (F11).
export async function getKpis(run: Run): Promise<import("./kpi").KpiRaw> {
  const r = await q<{ spike: number | null; holding: number; untrusted: number; decisions: number; reports: number }>(
    `select
       (select max(p_exceed) from forecasts where run_id=$1 and station_id='ward'
          and (ts at time zone 'Asia/Kolkata')::date = ($2::timestamptz at time zone 'Asia/Kolkata')::date + 1) as spike,
       (select count(distinct site_id)::int from safe_windows where run_id=$1 and status='avoid'
          and ts <= $2::timestamptz + interval '24 hours'
          and extract(hour from ts at time zone 'Asia/Kolkata') between 6 and 21) as holding,
       (select count(*)::int from sensor_audits where run_id=$1 and band='untrusted') as untrusted,
       (select count(*)::int from case_actions a join cases c on c.id = a.case_id
          where c.closed_at is null and a.phase='final' and a.status='proposed') as decisions,
       (select count(*)::int from citizen_reports cr join sites s on s.id = cr.site_id
          where s.ward_id=$3 and cr.status='new') as reports`,
    [run.id, run.issued_at, await ward()],
  );
  const x = r[0];
  return { spike_p_tomorrow: x.spike == null ? null : Number(x.spike), sites_holding: x.holding, untrusted: x.untrusted,
           decisions: x.decisions, new_reports: x.reports };
}

type BtBucket = { n: number; mae_model: number; mae_persistence: number; f1_exceed_model: number; f1_exceed_persistence: number; coverage_10_90: number; exceed_rate: number };
export interface Backtest {
  id: number; created_at: string; data_mode: string; stations: string[]; train_end: string; test_end: string; origins: number;
  metrics: Record<string, BtBucket>;
  spike_day: { day: string; actual_mean: number; issued_at: string | null; lead_hours?: number; forecast_mean?: number; p_exceed_max?: number; flagged?: boolean } | null;
  note: string | null;
}

export async function getLatestBacktest(kind: "standard" | "outage_replay" = "standard"): Promise<Backtest | null> {
  const r = await q<Backtest>(
    `select id, created_at, data_mode, stations, train_end, test_end, origins, metrics, spike_day, note
       from backtests where ward_id=$1 and kind=$2 order by created_at desc limit 1`, [await ward(), kind]);
  return r[0] ? { ...r[0], created_at: iso(r[0].created_at), train_end: iso(r[0].train_end), test_end: iso(r[0].test_end) } : null;
}

export interface Candidate { id: number; lat: number; lon: number; area_m2: number; site_id: string | null; scene_before: string; scene_after: string; found_at: string }

// Sentinel-2 change (F2): candidates not on the site list, largest first.
export async function getCandidates(limit = 8): Promise<{ unmatched: Candidate[]; matched: string[]; total: number }> {
  const rows = await q<Candidate>(
    `select id, lat, lon, area_m2, site_id, scene_before, scene_after, found_at from site_candidates
      where ward_id=$1 and status <> 'rejected' order by area_m2 desc`, [await ward()]);
  return {
    unmatched: rows.filter((r) => !r.site_id).slice(0, limit),
    matched: [...new Set(rows.filter((r) => r.site_id).map((r) => r.site_id as string))].sort(),
    total: rows.length,
  };
}

export interface DataCheck {
  id: number; run_id: number; checked_at: string; ok: boolean;
  shares: { hours: number; real: number; filled: number; synthetic: number };
  stations: { station_id: string; name?: string; newest: string | null; age_h: number | null; status: "fresh" | "stale" | "silent" }[];
  cams: Record<string, { hours: number; mae: number; bias: number; r: number | null; from?: string; to?: string }>;
  sources: { weather_live: number; receptors_osm: number; housing_osm?: number; sites_real: number; satellite_scene: string | null;
             satellite_found_at: string | null; run_issued_at: string; data_mode: string };
  problems: string[];
}

// The latest data check (issue #29), with station names joined in.
export async function getLatestDataCheck(): Promise<DataCheck | null> {
  const r = await q<DataCheck>(
    `select id, run_id, checked_at, ok, shares, stations, cams, sources, problems
       from data_checks where ward_id=$1 order by id desc limit 1`, [await ward()]);
  if (!r[0]) return null;
  const names = Object.fromEntries((await q<{ id: string; name: string }>(
    "select id, name from stations where ward_id=$1", [await ward()])).map((s) => [s.id, s.name]));
  const c = r[0];
  return { ...c, run_id: Number(c.run_id), checked_at: iso(c.checked_at),
           stations: c.stations.map((s) => ({ ...s, name: names[s.station_id] ?? s.station_id })) };
}

export interface Verification {
  id: number; site_id: string; site_name: string; action: string; station: string | null; window_start: string;
  during: number | null; baseline: number | null; change_pct: number | null; days: number;
  verdict: "drop" | "no_drop" | "insufficient"; note: string | null;
}
export interface FixMemory { action: string; n: number; mean_change_pct: number; drops: number }

// Verify (F12, issue #33): recent checks of whether PM10 fell after an action, and the average per action.
export async function getVerifications(limit = 12): Promise<{ recent: Verification[]; memory: FixMemory[] }> {
  const recent = await q<Verification>(
    `select v.id, v.site_id, s.name as site_name, v.action, st.name as station, v.window_start, v.during, v.baseline,
            v.change_pct, v.days, v.verdict, v.note
       from verifications v join sites s on s.id = v.site_id left join stations st on st.id = v.station_id
      where s.ward_id=$1 order by v.checked_at desc, v.id desc limit $2`, [await ward(), limit]);
  const memory = await q<FixMemory>(
    `select v.action, count(*)::int as n, round(avg(v.change_pct)::numeric, 1)::float as mean_change_pct,
            count(*) filter (where v.verdict = 'drop')::int as drops
       from verifications v join sites s on s.id = v.site_id
      where s.ward_id=$1 and v.verdict <> 'insufficient' group by v.action order by mean_change_pct`, [await ward()]);
  return { recent: recent.map((r) => ({ ...r, window_start: iso(r.window_start) })), memory };
}

export interface WeeklyData {
  forecast: { ts: string; p: number }[];
  observed: { ts: string; pm10: number }[];
  actions: { rule: string; action: string }[];
  inspections: { outcome: string }[];
  scores: { site_id: string; name: string; score: number; band: string; demo: boolean }[];
  checks: { verdict: string }[];
  real_hours: number; filled_or_synthetic_hours: number;
}

// Weekly ward report (F5, issue #37): the last 7 days. The forecast for each hour is the one issued
// at least 12 hours ahead (a day-ahead call); observed is the ward mean of measured station readings.
export async function getWeeklyData(): Promise<WeeklyData> {
  const [forecast, observed, actions, inspections, run, checks, mix] = await Promise.all([
    q<{ ts: string; p: number }>(
      `select distinct on (f.ts) f.ts, f.p_exceed as p from forecasts f join runs r on r.id = f.run_id
        where r.ward_id=$1 and f.station_id='ward' and f.ts > now() - interval '7 days' and f.ts <= now()
          and r.issued_at <= f.ts - interval '12 hours'
        order by f.ts, r.issued_at desc`, [await ward()]),
    q<{ ts: string; pm10: number }>(
      `select r.ts, avg(r.pm10)::float as pm10 from readings r join stations s on s.id = r.station_id
        where s.ward_id=$1 and not r.synthetic and r.pm10 is not null and r.ts > now() - interval '7 days'
        group by r.ts order by r.ts`, [await ward()]),
    q<{ rule: string; action: string }>(
      `select a.rule, a.action from case_actions a join cases c on c.id = a.case_id join sites s on s.id = c.site_id
        where s.ward_id=$1 and a.phase='final' and a.created_at > now() - interval '7 days'`, [await ward()]),
    q<{ outcome: string }>(
      `select i.outcome from inspections i join sites s on s.id = i.site_id where s.ward_id=$1 and i.at > now() - interval '7 days'`, [await ward()]),
    getLatestRun(),
    q<{ verdict: string }>(
      `select v.verdict from verifications v join sites s on s.id = v.site_id where s.ward_id=$1 and v.checked_at > now() - interval '7 days'`, [await ward()]),
    q<{ real: number; other: number }>(
      `select count(*) filter (where not r.synthetic)::int as real, count(*) filter (where r.synthetic)::int as other
         from readings r join stations s on s.id = r.station_id where s.ward_id=$1 and r.ts > now() - interval '7 days'`, [await ward()]),
  ]);
  const scores = run ? await q<{ site_id: string; name: string; score: number; band: string; demo: boolean }>(
    `select d.site_id, s.name, d.score, d.band, s.demo from dust_scores d join sites s on s.id = d.site_id
      where d.run_id=$1 order by d.score`, [run.id]) : [];
  return {
    forecast: forecast.map((x) => ({ ts: iso(x.ts), p: Number(x.p) })),
    observed: observed.map((x) => ({ ts: iso(x.ts), pm10: Number(x.pm10) })),
    actions, inspections, scores, checks,
    real_hours: mix[0]?.real ?? 0, filled_or_synthetic_hours: mix[0]?.other ?? 0,
  };
}
