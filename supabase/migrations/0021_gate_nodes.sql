-- D8 "ignored Safe-Work Windows" (issue #56): a DustTrace Node at a site's gate belongs to that site, so its
-- readings during an Avoid hour the manager accepted can show the window was not followed.

alter table nodes add column if not exists site_id text references sites(id) on delete set null;
create index if not exists nodes_site_idx on nodes (site_id) where site_id is not null;
