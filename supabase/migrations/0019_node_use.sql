-- DustTrace Nodes in the engine (issue #36): hourly PM from each node, and fix checks that can use a node.

create or replace view node_hourly with (security_invoker = true) as
  select node_id, date_trunc('hour', ts, 'UTC') as ts, avg(pm10_corrected) as pm10, avg(pm25_corrected) as pm25,
         count(*) as minutes
    from node_readings
   where pm10_corrected is not null
   group by node_id, date_trunc('hour', ts, 'UTC');

alter table verifications add column if not exists node_id text references nodes(id) on delete set null;
