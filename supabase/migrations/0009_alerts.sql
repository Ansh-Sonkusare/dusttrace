-- Ward alerts (PRD F11), derived per run. Each carries the action taken or needed.
-- Logged, not sent, in the prototype.

create table if not exists alerts (
  id        bigserial primary key,
  run_id    bigint not null references runs(id) on delete cascade,
  kind      text not null check (kind in ('critical', 'action', 'receptor', 'sensor')),
  site_id   text references sites(id) on delete cascade,
  case_id   bigint references cases(id) on delete set null,
  title     text not null,
  action    text not null,
  at        timestamptz not null default now()
);
create index if not exists alerts_run_idx on alerts (run_id);

alter table alerts enable row level security;
