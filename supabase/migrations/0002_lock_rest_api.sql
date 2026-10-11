-- Keep DustTrace tables off Supabase's public REST API.
-- The engine and the console connect to Postgres directly as the table owner, which bypasses RLS,
-- so enabling RLS with no policies only shuts out the API roles (anon, authenticated).
-- New tables need the same `enable row level security` line.

alter table wards          enable row level security;
alter table stations       enable row level security;
alter table readings       enable row level security;
alter table weather_hourly enable row level security;
alter table sites          enable row level security;
alter table receptors      enable row level security;
alter table runs           enable row level security;
alter table forecasts      enable row level security;
alter table plumes         enable row level security;
alter table exposures      enable row level security;
alter table safe_windows   enable row level security;

-- Run the view with the caller's permissions, so it can't be used to read past RLS.
alter view latest_run set (security_invoker = true);

-- On Supabase, also drop the API roles' grants, including on tables created later.
-- Plain Postgres has no such roles, so this is skipped there.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon')
     and exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on all tables in schema public from anon, authenticated;
    revoke all on all sequences in schema public from anon, authenticated;
    alter default privileges in schema public revoke all on tables from anon, authenticated;
    alter default privileges in schema public revoke all on sequences from anon, authenticated;
  end if;
end $$;
