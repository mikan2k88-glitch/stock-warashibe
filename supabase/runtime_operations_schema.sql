-- Runtime operations for endpoints 044-047.
-- Backend-only fail-closed; no public RLS policies.

create table if not exists public.stock_warashibe_runtime_status_snapshots (
  id bigint generated always as identity primary key,
  snapshot_key text not null unique,
  status text not null check (status in ('healthy','collecting','blocked','degraded')),
  summary jsonb not null default '{}'::jsonb,
  checks jsonb not null default '{}'::jsonb,
  github_sha text,
  github_run_id text,
  created_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_runtime_alerts (
  id bigint generated always as identity primary key,
  alert_key text not null unique,
  severity text not null check (severity in ('info','warning','critical')),
  category text not null,
  status text not null check (status in ('open','resolved','suppressed')),
  message text not null,
  evidence jsonb not null default '{}'::jsonb,
  github_sha text,
  github_run_id text,
  opened_at timestamptz not null default now(),
  resolved_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_evidence_integrity_audits (
  id bigint generated always as identity primary key,
  audit_key text not null unique,
  status text not null check (status in ('passed','collecting','failed')),
  observation_count integer not null default 0 check (observation_count >= 0),
  evaluated_count integer not null default 0 check (evaluated_count >= 0),
  checks jsonb not null default '{}'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  failures jsonb not null default '[]'::jsonb,
  github_sha text,
  github_run_id text,
  created_at timestamptz not null default now()
);

create table if not exists public.stock_warashibe_transition_audits (
  id bigint generated always as identity primary key,
  transition_key text not null unique,
  from_state text not null,
  to_state text not null,
  status text not null check (status in ('blocked','ready','applied','idempotent')),
  checks jsonb not null default '{}'::jsonb,
  action jsonb not null default '{}'::jsonb,
  live_trading_allowed boolean not null default false,
  broker_connected boolean not null default false,
  github_sha text,
  github_run_id text,
  created_at timestamptz not null default now()
);

alter table public.stock_warashibe_runtime_status_snapshots enable row level security;
alter table public.stock_warashibe_runtime_alerts enable row level security;
alter table public.stock_warashibe_evidence_integrity_audits enable row level security;
alter table public.stock_warashibe_transition_audits enable row level security;
