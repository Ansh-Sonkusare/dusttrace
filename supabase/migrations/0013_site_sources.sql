-- Real construction sites (issue #30): where each site came from, so OSM and satellite-confirmed
-- sites sit next to the labelled demo ones. Their BMC monitor feed isn't connected, so their
-- sensor_status is 'not_connected': unknown, not "no monitor".

alter table sites add column if not exists source text not null default 'seed';  -- seed | osm | satellite
alter table sites add column if not exists updated_at timestamptz not null default now();
create index if not exists sites_ward_source_idx on sites (ward_id, source);
