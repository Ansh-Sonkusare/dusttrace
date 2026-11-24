-- The PRD F3 forecast (issue #55): P(24 h mean PM10 > 100) for the three days after each run's issue time,
-- per station and for the ward, next to the hourly 72 h forecast in `forecasts`.

create table if not exists forecast_daily (
  run_id      bigint not null references runs(id) on delete cascade,
  station_id  text not null,                 -- station id, or 'ward' for the hourly mean of the run's stations
  day         smallint not null check (day between 1 and 3),  -- hours 1-24, 25-48, 49-72 after issued_at
  starts_at   timestamptz not null,          -- first forecast hour of the day
  ends_at     timestamptz not null,          -- last forecast hour of the day
  p_exceed    real not null check (p_exceed between 0 and 1),  -- P(24 h mean PM10 > 100)
  primary key (run_id, station_id, day)
);

alter table forecast_daily enable row level security;

-- Back-test scores for those daily calls against the 24 h means the stations measured.
alter table backtests add column if not exists daily jsonb;
