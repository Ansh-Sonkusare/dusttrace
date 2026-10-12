-- Discover (PRD F2): changed ground found in Sentinel-2 scenes. A candidate near a known site confirms
-- it is active; an unmatched one is a possible unregistered site, unverified until someone looks.

create table if not exists site_candidates (
  id             bigserial primary key,
  ward_id        text not null references wards(id),
  found_at       timestamptz not null default now(),
  scene_before   text not null,
  scene_after    text not null,
  lat            double precision not null,
  lon            double precision not null,
  area_m2        real not null,
  site_id        text references sites(id) on delete set null,   -- matched known site, if any
  status         text not null default 'unverified' check (status in ('unverified', 'confirmed', 'rejected'))
);
create index if not exists site_candidates_ward_idx on site_candidates (ward_id, found_at desc);

alter table site_candidates enable row level security;
