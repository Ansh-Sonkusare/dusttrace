-- Citizen reports with a photo and a place (PRD F2, F8; issue #57). A report from a site's QR page keeps
-- its site; one from the page for places with no site must carry the resident's position and its ward.
-- An officer verifies or rejects each report in the console. Photos may show people: they are served only
-- behind the console password.

alter table citizen_reports alter column site_id drop not null;
alter table citizen_reports add column if not exists ward_id text references wards(id);
alter table citizen_reports add column if not exists lat double precision;
alter table citizen_reports add column if not exists lon double precision;
alter table citizen_reports add column if not exists accuracy_m real;      -- as the phone reported it
alter table citizen_reports add column if not exists reviewed_at timestamptz;

update citizen_reports c set ward_id = s.ward_id from sites s where s.id = c.site_id and c.ward_id is null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'citizen_reports_site_or_place') then
    alter table citizen_reports add constraint citizen_reports_site_or_place
      check (site_id is not null or (lat is not null and lon is not null and ward_id is not null));
  end if;
end $$;
create index if not exists citizen_reports_ward_status_idx on citizen_reports (ward_id, status, at desc);

-- One photo per report: a JPEG the page shrank and the server stripped of EXIF. The label columns are
-- for the vision model (a later issue) and stay empty until it runs.
create table if not exists report_photos (
  report_id         bigint primary key references citizen_reports(id) on delete cascade,
  jpeg              bytea not null,
  width             int not null,
  height            int not null,
  label             text,
  label_confidence  real check (label_confidence between 0 and 1),
  label_model       text
);

alter table report_photos enable row level security;

-- What each Dust Score was computed from (verified reports, violations, spike hours ...), so a change can be traced.
alter table dust_scores add column if not exists inputs jsonb not null default '{}'::jsonb;
