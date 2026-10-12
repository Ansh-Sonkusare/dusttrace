-- Site-manager plan (PRD F7): a manager accepts the day's Safe-Work Windows and misting schedule.
-- Accepted plans feed "Safe-Work Windows followed" in the Dust Score.

create table if not exists plan_acceptances (
  id           bigserial primary key,
  site_id      text not null references sites(id) on delete cascade,
  run_id       bigint references runs(id) on delete set null,
  avoid_hours  integer not null default 0,
  accepted_by  text,
  accepted_at  timestamptz not null default now()
);
create index if not exists plan_acceptances_site_at_idx on plan_acceptances (site_id, accepted_at desc);

alter table plan_acceptances enable row level security;
