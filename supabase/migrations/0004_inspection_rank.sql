-- Attribute and prioritise (PRD F4): the ranked "Inspect today" list for each run.
-- `components` holds each term of the priority score (0-100 points); `reasons` the top two in words.

create table if not exists inspection_rank (
  run_id      bigint not null references runs(id) on delete cascade,
  site_id     text not null references sites(id) on delete cascade,
  rank        integer not null,
  score       real not null,
  components  jsonb not null default '{}'::jsonb,
  reasons     text[] not null default '{}',
  primary key (run_id, site_id)
);

alter table inspection_rank enable row level security;
