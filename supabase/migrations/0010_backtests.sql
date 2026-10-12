-- Forecast back-tests (PRD F3 evidence): replays with only the data up to each origin visible.

create table if not exists backtests (
  id          bigserial primary key,
  created_at  timestamptz not null default now(),
  ward_id     text not null references wards(id),
  data_mode   text not null,          -- 'live' when every reading used is real
  stations    text[] not null default '{}',
  train_end   timestamptz not null,
  test_end    timestamptz not null,
  origins     integer not null,
  metrics     jsonb not null default '{}'::jsonb,
  spike_day   jsonb,
  note        text
);

alter table backtests enable row level security;
