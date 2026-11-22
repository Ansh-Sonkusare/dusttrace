-- DustTrace Nodes (PRD F9, issue #36): low-cost monitors at schools, hospitals and housing societies.

create table if not exists nodes (
  id            text primary key check (id ~ '^node-[a-z0-9-]{1,48}$'),
  ward_id       text not null references wards(id),
  name          text not null,
  host_kind     text not null check (host_kind in ('school', 'hospital', 'housing', 'site_gate', 'other')),
  receptor_id   text references receptors(id) on delete set null,
  lat           double precision not null,
  lon           double precision not null,
  key_hash      text not null,
  active        boolean not null default true,
  created_at    timestamptz not null default now(),
  last_seen_at  timestamptz
);

create table if not exists node_readings (
  node_id         text not null references nodes(id) on delete cascade,
  ts              timestamptz not null,
  pm25_raw        real not null,
  pm10_raw        real not null,
  temp            real,
  rh              real,
  pm25_corrected  real,
  pm10_corrected  real,
  received_at     timestamptz not null default now(),
  primary key (node_id, ts)
);
create index if not exists node_readings_ts_idx on node_readings (ts desc);

alter table nodes enable row level security;
alter table node_readings enable row level security;
