-- Officer app (PRD F6): inspection outcomes logged in the field. Confirmed violations feed the
-- priority score (past violations) and the agent (D8, D9).

create table if not exists inspections (
  id        bigserial primary key,
  site_id   text not null references sites(id) on delete cascade,
  case_id   bigint references cases(id) on delete set null,
  outcome   text not null check (outcome in ('violation', 'compliant', 'closed', 'no_access')),
  note      text,
  officer   text,
  at        timestamptz not null default now()
);
create index if not exists inspections_site_at_idx on inspections (site_id, at desc);

alter table inspections enable row level security;
