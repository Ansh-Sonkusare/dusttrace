-- Public read API (PRD F5, issue #37): one row per request, keyed by a salted hash of the address,
-- only to rate-limit. Rows older than a day are pruned on write.

create table if not exists api_requests (
  id       bigserial primary key,
  ip_hash  text not null,
  path     text not null,
  at       timestamptz not null default now()
);
create index if not exists api_requests_ip_idx on api_requests (ip_hash, at desc);

alter table api_requests enable row level security;
