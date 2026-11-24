-- Person-exposure avoided (PRD F7 metric, issue #59): people x PM10 a site adds where they are (µg/m³) x hours,
-- without DustTrace (dusty work every allowed hour, 06:00-22:00 IST) and with the plan (each Avoid hour's work moved
-- to the cleanest open hour of the same day, its dust there counted). Definition in services/engine/dusttrace/exposure.py.
-- Each figure comes twice: over every receptor however faint the increment (the headline), and over the receptors
-- given 15 µg/m³ or more (`_15`: the `exposures` rows, so it can be checked by hand).

-- Per site hour: the hour's person-exposure and, for an Avoid hour, where its work moves and what that keeps off people.
alter table safe_windows add column if not exists person_exposure real not null default 0;
alter table safe_windows add column if not exists person_exposure_15 real not null default 0;
alter table safe_windows add column if not exists move_to timestamptz;           -- null: nothing to move, or no better hour
alter table safe_windows add column if not exists avoided real not null default 0;
alter table safe_windows add column if not exists avoided_15 real not null default 0;
-- The part of person_exposure from receptors inside the ward's boundary. Home cells in neighbouring wards get this
-- ward's housing density, an estimate rather than a census count.
alter table safe_windows add column if not exists person_exposure_ward real not null default 0;

-- Per site and run, over the run's 48 h.
create table if not exists exposure_avoided (
  run_id        bigint not null references runs(id) on delete cascade,
  site_id       text not null references sites(id) on delete cascade,
  without_plan  double precision not null,          -- person·µg/m³·h, every receptor
  with_plan     double precision not null,
  avoided       double precision not null check (avoided >= 0),
  avoided_pct   real,                               -- null when nothing reaches anyone without the plan
  without_15    double precision not null,          -- the same over receptors given 15 µg/m³ or more
  with_15       double precision not null,
  avoided_15    double precision not null check (avoided_15 >= 0),
  avoided_15_pct real,
  moved_hours   integer not null default 0,         -- Avoid hours whose work moves
  stuck_hours   integer not null default 0,         -- Avoid hours with no better hour that day
  primary key (run_id, site_id)
);

alter table exposure_avoided add column if not exists without_ward double precision not null default 0;
alter table exposure_avoided add column if not exists avoided_ward double precision not null default 0;  -- can dip below 0

alter table exposure_avoided enable row level security;

-- Ward totals per run for real sites, demo sites apart. "Accepted" is what the plans site managers accepted from this
-- run keep off people: the run's moves from the acceptance to the end of the plan's 24 h, each site hour counted once,
-- for the latest plan the site accepted before that hour. Real sites only; whether the work moved is not checked.
create or replace view exposure_avoided_ward with (security_invoker = true) as
  select r.id as run_id, r.ward_id, r.issued_at,
         count(*) filter (where not s.demo)::int as sites,
         coalesce(sum(e.without_plan) filter (where not s.demo), 0) as without_plan,
         coalesce(sum(e.with_plan) filter (where not s.demo), 0) as with_plan,
         coalesce(sum(e.avoided) filter (where not s.demo), 0) as avoided,
         round((100 * sum(e.avoided) filter (where not s.demo)
                / nullif(sum(e.without_plan) filter (where not s.demo), 0))::numeric, 1)::real as avoided_pct,
         coalesce(sum(e.without_15) filter (where not s.demo), 0) as without_15,
         coalesce(sum(e.avoided_15) filter (where not s.demo), 0) as avoided_15,
         round((100 * sum(e.avoided_15) filter (where not s.demo)
                / nullif(sum(e.without_15) filter (where not s.demo), 0))::numeric, 1)::real as avoided_15_pct,
         count(*) filter (where not s.demo and e.moved_hours + e.stuck_hours > 0)::int as sites_with_avoid,
         coalesce(sum(e.moved_hours) filter (where not s.demo), 0)::int as moved_hours,
         coalesce(sum(e.stuck_hours) filter (where not s.demo), 0)::int as stuck_hours,
         count(*) filter (where s.demo)::int as demo_sites,
         coalesce(sum(e.avoided) filter (where s.demo), 0) as demo_avoided,
         a.plans as accepted_plans, a.sites as accepted_sites, a.avoided as accepted_avoided,
         a.avoided_15 as accepted_avoided_15,
         coalesce(sum(e.without_ward) filter (where not s.demo), 0) as without_ward,
         coalesce(sum(e.avoided_ward) filter (where not s.demo), 0) as avoided_ward,
         round((100 * sum(e.avoided_ward) filter (where not s.demo)
                / nullif(sum(e.without_ward) filter (where not s.demo), 0))::numeric, 1)::real as avoided_ward_pct
    from runs r
    join exposure_avoided e on e.run_id = r.id
    join sites s on s.id = e.site_id
    cross join lateral (
      select count(distinct p.id)::int as plans, count(distinct p.site_id)::int as sites,
             coalesce(sum(w.avoided), 0) as avoided, coalesce(sum(w.avoided_15), 0) as avoided_15
        from plan_acceptances p
        join sites ps on ps.id = p.site_id and not ps.demo
        join safe_windows w on w.run_id = p.run_id and w.site_id = p.site_id
       where p.run_id = r.id and w.move_to >= p.accepted_at and w.ts >= p.accepted_at
         and w.ts <= r.issued_at + interval '24 hours'
         and not exists (select 1 from plan_acceptances q where q.site_id = p.site_id and q.accepted_at <= w.ts
                           and (q.accepted_at, q.id) > (p.accepted_at, p.id))) a
   group by r.id, r.ward_id, r.issued_at, a.plans, a.sites, a.avoided, a.avoided_15;
