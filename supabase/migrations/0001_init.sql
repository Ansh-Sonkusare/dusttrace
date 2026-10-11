-- DustTrace core schema (milestone 1: real-data core)
-- Runs on Supabase Postgres or any Postgres 15+ with PostGIS.

create extension if not exists postgis;

-- Wards we cover. Milestone 1 is K-East (Andheri East) only.
create table if not exists wards (
  id          text primary key,
  name        text not null,
  center_lat  double precision not null,
  center_lon  double precision not null,
  bbox        double precision[] not null  -- [min_lon, min_lat, max_lon, max_lat]
);

-- Air-quality stations (CPCB / MPCB CAAQMS via OpenAQ, or seed placeholders).
create table if not exists stations (
  id          text primary key,
  name        text not null,
  source      text not null,               -- 'openaq' | 'seed'
  lat         double precision not null,
  lon         double precision not null,
  geom        geography(Point, 4326) generated always as
                (st_setsrid(st_makepoint(lon, lat), 4326)::geography) stored,
  ward_id     text references wards(id),
  meta        jsonb not null default '{}'::jsonb
);

-- Hourly PM readings. `synthetic` marks generated history used when live data is unavailable.
create table if not exists readings (
  station_id  text not null references stations(id) on delete cascade,
  ts          timestamptz not null,
  pm10        real,
  pm25        real,
  synthetic   boolean not null default false,
  primary key (station_id, ts)
);
create index if not exists readings_ts_idx on readings (ts);

-- Hourly weather for a ward (observed past + forecast future, from Open-Meteo).
create table if not exists weather_hourly (
  ward_id     text not null references wards(id) on delete cascade,
  ts          timestamptz not null,
  wind_speed  real,   -- m/s at 10 m
  wind_dir    real,   -- degrees, direction the wind blows FROM
  blh         real,   -- boundary-layer (mixing) height, m
  temp        real,   -- deg C
  rh          real,   -- %
  precip      real,   -- mm
  is_forecast boolean not null default false,
  synthetic   boolean not null default false,
  fetched_at  timestamptz not null default now(),
  primary key (ward_id, ts)
);

-- Construction sites. Milestone 1 seeds demo sites; `demo` flags them in the UI.
create table if not exists sites (
  id            text primary key,
  name          text not null,
  activity      text not null,             -- demolition | excavation | structure | debris
  developer     text,
  lat           double precision not null,
  lon           double precision not null,
  geom          geography(Point, 4326) generated always as
                  (st_setsrid(st_makepoint(lon, lat), 4326)::geography) stored,
  ward_id       text references wards(id),
  area_m2       real not null default 5000,
  sensor_status text not null default 'unknown', -- trusted | untrusted | none | unknown
  demo          boolean not null default true
);

-- People and places downwind: schools, hospitals, housing.
create table if not exists receptors (
  id          text primary key,
  name        text not null,
  kind        text not null check (kind in ('school', 'hospital', 'housing')),
  lat         double precision not null,
  lon         double precision not null,
  geom        geography(Point, 4326) generated always as
                (st_setsrid(st_makepoint(lon, lat), 4326)::geography) stored,
  ward_id     text references wards(id),
  population  integer not null default 500,
  source      text not null default 'seed'  -- 'osm' | 'seed'
);

-- One row per engine run; everything downstream hangs off a run.
create table if not exists runs (
  id          bigserial primary key,
  created_at  timestamptz not null default now(),
  ward_id     text not null references wards(id),
  issued_at   timestamptz not null,          -- forecast origin (t0)
  data_mode   text not null,                 -- 'live' | 'synthetic' | 'mixed'
  model       text not null,
  metrics     jsonb not null default '{}'::jsonb
);

-- Ward-level and station-level PM10 forecast, hourly for 48 h.
create table if not exists forecasts (
  run_id      bigint not null references runs(id) on delete cascade,
  station_id  text not null,                 -- station id, or 'ward' for the ward aggregate
  ts          timestamptz not null,
  pm10        real not null,
  pm10_lo     real not null,
  pm10_hi     real not null,
  p_exceed    real not null,                 -- P(PM10 > 100)
  primary key (run_id, station_id, ts)
);

-- Plume footprint per site per forecast hour (area above the threshold).
create table if not exists plumes (
  run_id      bigint not null references runs(id) on delete cascade,
  site_id     text not null references sites(id) on delete cascade,
  ts          timestamptz not null,
  geom        geometry(Polygon, 4326),
  max_conc    real not null,                 -- peak ground-level increment, ug/m3
  length_m    real not null,
  primary key (run_id, site_id, ts)
);

-- Who the plume reaches, per site per hour.
create table if not exists exposures (
  run_id      bigint not null references runs(id) on delete cascade,
  site_id     text not null references sites(id) on delete cascade,
  receptor_id text not null references receptors(id) on delete cascade,
  ts          timestamptz not null,
  conc        real not null,                 -- modelled increment at the receptor, ug/m3
  primary key (run_id, site_id, receptor_id, ts)
);

-- Safe-Work Windows: go / caution / avoid per site per hour.
create table if not exists safe_windows (
  run_id          bigint not null references runs(id) on delete cascade,
  site_id         text not null references sites(id) on delete cascade,
  ts              timestamptz not null,
  status          text not null check (status in ('go', 'caution', 'avoid')),
  exposed_people  integer not null default 0,
  sensitive_hit   boolean not null default false,
  reason          text not null,
  primary key (run_id, site_id, ts)
);

create or replace view latest_run as
  select distinct on (ward_id) * from runs order by ward_id, created_at desc;
