-- Shadow readiness audit trail for endpoints 034-037.
-- RLS is intentionally enabled without public policies: backend-only/fail-closed.

create table if not exists public.stock_warashibe_shadow_readiness_audits (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  strategy_key text not null,
  status text not null check (status in ('collecting','accepted','rejected','blocked')),
  observation_days integer not null default 0 check (observation_days >= 0),
  evaluated_buy_signals integer not null default 0 check (evaluated_buy_signals >= 0),
  readiness jsonb not null default '{}'::jsonb,
  acceptance jsonb not null default '{}'::jsonb,
  failure_diagnosis jsonb not null default '{}'::jsonb,
  reopen_gate jsonb not null default '{}'::jsonb,
  paper_trading_allowed boolean not null default false,
  live_trading_allowed boolean not null default false,
  human_gate_required boolean not null default true,
  github_sha text,
  github_run_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.stock_warashibe_shadow_readiness_audits enable row level security;
