-- Paper/live preparation schema for endpoints 038-043.
-- No broker credentials or real-order transport are included.
-- RLS remains fail-closed/backend-only.

alter table public.stock_warashibe_paper_orders
  add column if not exists exit_price numeric,
  add column if not exists net_pnl numeric,
  add column if not exists capital_after numeric,
  add column if not exists filled_at timestamptz,
  add column if not exists closed_at timestamptz;

create table if not exists public.stock_warashibe_paper_performance_audits (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  session_key text,
  strategy_key text not null,
  status text not null check (status in ('blocked','collecting','qualified')),
  paper_days integer not null default 0 check (paper_days >= 0),
  closed_trades integer not null default 0 check (closed_trades >= 0),
  metrics jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  live_trading boolean not null default false check (live_trading = false),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_human_gate_packages (
  id bigint generated always as identity primary key,
  package_key text not null unique,
  strategy_key text not null,
  status text not null check (status in ('blocked','ready_for_review','approved','rejected')),
  limits jsonb not null default '{}'::jsonb,
  safeguards jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  explicit_human_approval boolean not null default false,
  approved_at timestamptz,
  live_trading_allowed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_real_trial_intents (
  id bigint generated always as identity primary key,
  intent_key text not null unique,
  strategy_key text not null,
  symbol text,
  status text not null check (status in ('blocked','ready_for_manual_execution','executed','cancelled')),
  trial_payload jsonb not null default '{}'::jsonb,
  human_gate_package_key text,
  explicit_human_approval boolean not null default false,
  broker_connected boolean not null default false,
  live_order_sent boolean not null default false,
  execution_receipt jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.stock_warashibe_paper_performance_audits enable row level security;
alter table public.stock_warashibe_human_gate_packages enable row level security;
alter table public.stock_warashibe_real_trial_intents enable row level security;
