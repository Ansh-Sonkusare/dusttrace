-- Sensor Audit (PRD F1): the sensor BMC requires on every site, its readings, and how far to trust it.
-- Until BMC shares the site feed, sensors are simulated from real ambient data with a labelled fault
-- injected (`injected_fault` is the simulator's ground truth), and every reading is synthetic.

create table if not exists site_sensors (
  id             text primary key,
  site_id        text not null references sites(id) on delete cascade,
  vendor         text,
  has_relay      boolean not null default false,  -- can switch misting remotely (D2, D4)
  simulated      boolean not null default true,
  injected_fault text                              -- none | flatline | dropout | too_clean | drift | rh_bias
);

create table if not exists site_readings (
  sensor_id  text not null references site_sensors(id) on delete cascade,
  ts         timestamptz not null,
  pm10       real,
  pm25       real,
  rh         real,
  synthetic  boolean not null default true,
  primary key (sensor_id, ts)
);
create index if not exists site_readings_ts_idx on site_readings (ts);

-- Trust score per sensor per run: 0-100, band, each check's result and plain reasons.
create table if not exists sensor_audits (
  run_id     bigint not null references runs(id) on delete cascade,
  sensor_id  text not null references site_sensors(id) on delete cascade,
  site_id    text not null references sites(id) on delete cascade,
  score      real not null,
  band       text not null check (band in ('trusted', 'check', 'untrusted')),
  checks     jsonb not null default '{}'::jsonb,
  reasons    text[] not null default '{}',
  primary key (run_id, sensor_id)
);

alter table site_sensors  enable row level security;
alter table site_readings enable row level security;
alter table sensor_audits enable row level security;
