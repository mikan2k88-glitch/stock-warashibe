-- Stock Warashibe v0.1 experiment storage schema
-- Canonical schema for research/backtest evidence.

create table if not exists public.stock_warashibe_experiment_runs (
  id bigint generated always as identity primary key,
  run_key text not null unique,
  scenario_key text not null,
  mode text not null default 'simulation',
  starting_capital numeric not null check (starting_capital >= 0),
  config jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_strategy_results (
  id bigint generated always as identity primary key,
  run_key text not null references public.stock_warashibe_experiment_runs(run_key) on delete cascade,
  strategy text not null,
  traded boolean not null default false,
  final_capital numeric not null check (final_capital >= 0),
  total_return numeric,
  max_drawdown numeric,
  win_rate numeric,
  profit_factor numeric,
  trade_count integer not null default 0 check (trade_count >= 0),
  metrics jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_key, strategy)
);

create table if not exists public.stock_warashibe_trade_history (
  id bigint generated always as identity primary key,
  run_key text not null references public.stock_warashibe_experiment_runs(run_key) on delete cascade,
  strategy text not null,
  trade_index integer not null check (trade_index >= 0),
  symbol text not null,
  entry_date date,
  exit_date date,
  buy_price numeric,
  sell_price numeric,
  shares integer check (shares is null or shares >= 0),
  fees numeric,
  net_pnl numeric,
  capital_before numeric,
  capital_after numeric,
  trade jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_key, strategy, trade_index)
);

create table if not exists public.stock_warashibe_research_decisions (
  id bigint generated always as identity primary key,
  decision_key text not null unique,
  run_key text references public.stock_warashibe_experiment_runs(run_key) on delete set null,
  strategic_question text not null,
  decision text not null,
  rationale text not null,
  evidence jsonb not null default '{}'::jsonb,
  status text not null default 'active'
    check (status in ('active','superseded','invalidated','completed')),
  decided_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

alter table public.stock_warashibe_experiment_runs enable row level security;
alter table public.stock_warashibe_strategy_results enable row level security;
alter table public.stock_warashibe_trade_history enable row level security;
alter table public.stock_warashibe_research_decisions enable row level security;
