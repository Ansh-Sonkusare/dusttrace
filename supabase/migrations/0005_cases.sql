-- Dust Response Agent (PRD F12): cases and the actions the policy engine picked under rules D1-D10.
-- One open case per site; each run updates it. Officer decisions and evidence deadlines persist.

create table if not exists cases (
  id             bigserial primary key,
  site_id        text not null references sites(id) on delete cascade,
  opened_run_id  bigint references runs(id) on delete set null,
  last_run_id    bigint references runs(id) on delete set null,
  opened_at      timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  closed_at      timestamptz,
  state          text not null,
  triggers       text[] not null default '{}',
  signals        text[] not null default '{}',
  hypotheses     jsonb not null default '[]'::jsonb,   -- [[cause, p], ...]
  what_changed   text,
  stop_reason    text
);
create unique index if not exists cases_one_open_per_site on cases (site_id) where closed_at is null;

create table if not exists case_actions (
  id          bigserial primary key,
  case_id     bigint not null references cases(id) on delete cascade,
  phase       text not null check (phase in ('initial', 'final')),
  action      text not null,
  type        text not null,
  route       text not null check (route in ('auto', 'site', 'L1', 'L2')),
  rule        text not null,
  reason      text not null,
  status      text not null check (status in ('done', 'sent', 'proposed', 'approved', 'declined',
                                              'requested', 'answered', 'expired')),
  at          timestamptz,          -- when it should happen (scheduled mist)
  deadline    timestamptz,          -- evidence requests; never extended
  decided_by  text,
  decided_at  timestamptz,
  created_at  timestamptz not null default now(),
  unique (case_id, phase, action, rule)
);

alter table cases        enable row level security;
alter table case_actions enable row level security;
