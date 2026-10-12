-- Dust Score (PRD F8) per site per run, and citizen reports from the public site page (QR).

create table if not exists dust_scores (
  run_id      bigint not null references runs(id) on delete cascade,
  site_id     text not null references sites(id) on delete cascade,
  score       real not null,
  band        text not null check (band in ('good', 'fair', 'poor')),
  components  jsonb not null default '{}'::jsonb,
  notes       text[] not null default '{}',
  primary key (run_id, site_id)
);

create table if not exists citizen_reports (
  id        bigserial primary key,
  site_id   text not null references sites(id) on delete cascade,
  kind      text not null check (kind in ('uncovered_debris', 'no_barricade', 'dry_excavation', 'uncovered_truck', 'other')),
  note      text,
  status    text not null default 'new' check (status in ('new', 'verified', 'rejected')),
  ip_hash   text,          -- salted hash, only for rate limiting
  at        timestamptz not null default now()
);
create index if not exists citizen_reports_site_at_idx on citizen_reports (site_id, at desc);
create index if not exists citizen_reports_ip_at_idx on citizen_reports (ip_hash, at desc);

alter table dust_scores     enable row level security;
alter table citizen_reports enable row level security;
