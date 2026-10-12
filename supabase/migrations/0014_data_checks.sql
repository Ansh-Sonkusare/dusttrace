-- Data check (issue #29): after each run, how much of it rests on real data. One row per check.

create table if not exists data_checks (
  id            bigserial primary key,
  ward_id       text not null references wards(id),
  run_id        bigint references runs(id) on delete cascade,
  checked_at    timestamptz not null default now(),
  ok            boolean not null,
  shares        jsonb not null default '{}'::jsonb,   -- last week's station hours: real | filled | synthetic
  stations      jsonb not null default '[]'::jsonb,   -- per real station: newest reading, age, status
  cams          jsonb not null default '{}'::jsonb,   -- per station: hold-out error of the CAMS fill
  sources       jsonb not null default '{}'::jsonb,   -- weather, receptors, sites, satellite
  problems      jsonb not null default '[]'::jsonb    -- plain sentences for what isn't real
);
create index if not exists data_checks_ward_idx on data_checks (ward_id, checked_at desc);

alter table data_checks enable row level security;
