-- Forward-only research observations for G6.
-- RLS is enabled without public policies: backend-only/fail-closed.

create table if not exists public.stock_warashibe_shadow_observations (
  id bigint generated always as identity primary key,
  observation_key text not null unique,
  observation_date date not null,
  strategy_key text not null,
  symbol text not null,
  sector text,
  signal text not null check (signal in ('buy','skip')),
  score numeric not null,
  reference_close numeric not null check (reference_close > 0),
  lot_cost numeric not null check (lot_cost > 0),
  shares integer not null default 100 check (shares = 100),
  reason text,
  source_sha256 text,
  status text not null default 'pending'
    check (status in ('pending','evaluated','skipped')),
  outcome jsonb not null default '{}'::jsonb,
  evaluated_at timestamptz,
  live_trading boolean not null default false check (live_trading = false),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.stock_warashibe_shadow_observations enable row level security;
