-- Copernicus CAMS model PM at each real station's position (issue #28), kept apart from real readings.
-- Used, corrected per station, only to fill hours when the CPCB feed is down; filled hours are flagged.

create table if not exists cams_hourly (
  station_id  text not null references stations(id) on delete cascade,
  ts          timestamptz not null,
  pm10        real,
  pm25        real,
  fetched_at  timestamptz not null default now(),
  primary key (station_id, ts)
);
create index if not exists cams_hourly_ts_idx on cams_hourly (ts);

alter table backtests add column if not exists kind text not null default 'standard';

alter table cams_hourly enable row level security;
