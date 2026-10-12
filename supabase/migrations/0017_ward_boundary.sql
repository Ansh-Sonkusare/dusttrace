-- Second pilot ward (issue #35): each ward's real boundary (OpenStreetMap, simplified GeoJSON Polygon),
-- so housing, sites and the map use the ward itself rather than its bounding box.

alter table wards add column if not exists boundary jsonb;

-- A refreshed OSM pull can drop a site (finished, or outside the ward's real boundary). Retired sites
-- keep their history but are no longer planned.
alter table sites add column if not exists active boolean not null default true;
