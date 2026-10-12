-- Verify (PRD F12, issue #33): did PM10 fall after the agent acted? One row per checked action.

create table if not exists verifications (
  id            bigserial primary key,
  action_id     bigint not null unique references case_actions(id) on delete cascade,
  case_id       bigint not null references cases(id) on delete cascade,
  site_id       text not null references sites(id) on delete cascade,
  action        text not null,
  station_id    text references stations(id) on delete set null,
  window_start  timestamptz not null,
  window_end    timestamptz not null,
  during        real,            -- mean PM10 at the station in the window
  baseline      real,            -- same hours on earlier days with the same wind
  change_pct    real,
  days          integer not null default 0,
  verdict       text not null check (verdict in ('drop', 'no_drop', 'insufficient')),
  note          text,
  checked_at    timestamptz not null default now()
);
create index if not exists verifications_site_idx on verifications (site_id, checked_at desc);

alter table verifications enable row level security;
