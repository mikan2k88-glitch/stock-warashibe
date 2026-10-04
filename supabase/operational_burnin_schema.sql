-- Operational burn-in and safe recovery for endpoints 048-049.
-- Backend-only fail-closed; no public RLS policies.

create table if not exists public.stock_warashibe_burnin_audits (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  status text not null check (status in ('collecting','passed','failed')),
  observed_business_days integer not null default 0 check (observed_business_days >= 0),
  target_business_days integer not null default 5 check (target_business_days >= 1),
  checks jsonb not null default '{}'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  failures jsonb not null default '[]'::jsonb,
  github_sha text,
  github_run_id text,
  created_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_recovery_audits (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  status text not null check (status in ('idle','retrying','recovered','blocked')),
  trigger_categories jsonb not null default '[]'::jsonb,
  safe_actions jsonb not null default '[]'::jsonb,
  retry_policy jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  live_trading_allowed boolean not null default false,
  broker_connected boolean not null default false,
  github_sha text,
  github_run_id text,
  created_at timestamptz not null default now()
);

alter table public.stock_warashibe_burnin_audits enable row level security;
alter table public.stock_warashibe_recovery_audits enable row level security;
