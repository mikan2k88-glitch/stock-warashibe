-- Stock Warashibe pre-live research schema.
-- RLS is intentionally enabled without public policies: backend-only/fail-closed.

create table if not exists public.stock_warashibe_universe_lifecycle (
  id bigint generated always as identity primary key,
  lifecycle_key text not null unique,
  symbol text not null,
  company_name text,
  listed_at date,
  delisted_at date,
  market_segment text,
  lifecycle_status text not null check (lifecycle_status in ('current','delisted','unknown')),
  source_key text not null,
  source_url text not null,
  snapshot_date date not null,
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_paper_sessions (
  id bigint generated always as identity primary key,
  session_key text not null unique,
  strategy_key text not null,
  starting_capital numeric not null check (starting_capital >= 0),
  current_capital numeric not null check (current_capital >= 0),
  status text not null check (status in ('blocked','ready','active','completed','stopped')),
  readiness jsonb not null default '{}'::jsonb,
  ledger jsonb not null default '{}'::jsonb,
  live_trading boolean not null default false check (live_trading = false),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_paper_orders (
  id bigint generated always as identity primary key,
  order_key text not null unique,
  session_key text not null,
  symbol text not null,
  decision_date date not null,
  side text not null check (side in ('buy','sell')),
  shares integer not null check (shares > 0),
  expected_price numeric,
  fill_price numeric,
  fees numeric not null default 0 check (fees >= 0),
  status text not null check (status in ('blocked','proposed','approved','filled','closed','cancelled')),
  approval_required boolean not null default true,
  approved_at timestamptz,
  order_payload jsonb not null default '{}'::jsonb,
  live_order boolean not null default false check (live_order = false),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_approval_requests (
  id bigint generated always as identity primary key,
  request_key text not null unique,
  session_key text not null,
  symbol text,
  approval_code_hint text not null default '8888',
  status text not null check (status in ('blocked','pending','approved','rejected','expired')),
  payload jsonb not null default '{}'::jsonb,
  expires_at timestamptz,
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_live_readiness_audits (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  strategy_key text not null,
  status text not null check (status in ('blocked','ready_for_human_gate')),
  checks jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  live_trading_allowed boolean not null default false,
  human_gate_required boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.stock_warashibe_universe_lifecycle enable row level security;
alter table public.stock_warashibe_paper_sessions enable row level security;
alter table public.stock_warashibe_paper_orders enable row level security;
alter table public.stock_warashibe_approval_requests enable row level security;
alter table public.stock_warashibe_live_readiness_audits enable row level security;
