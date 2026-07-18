-- Credit packs, and report-denominated billing.
--
-- Analyses are now the primary quota; minutes remain only as a secondary
-- abuse guard with generous headroom. Credits are a one-off purchased balance
-- consumed after the monthly allowance is spent.
--
-- Unlike the monthly counters, credits are NOT period-scoped: the monthly
-- reset must never touch them, and a refund is never guarded by usage_month.
--
-- Idempotent: safe to re-run.

alter table public.profiles
  add column if not exists credits integer not null default 0;

-- 1 when a purchased credit funded the job, else 0 (the monthly allowance
-- did). Also the funding-pool marker: it decides whether completion charges
-- the monthly counter and whether failure refunds a credit.
alter table public.analysis_jobs
  add column if not exists charged_credits integer not null default 0;

-- The monthly quota check counts only monthly-funded work in flight, so it
-- filters on charged_credits alongside user and status.
create index if not exists analysis_jobs_user_funding_idx
  on public.analysis_jobs (user_id, status, charged_credits);

-- Stripe event ids already applied.
--
-- Stripe redelivers on any non-2xx and on its own schedule, so handlers must
-- be idempotent. The id is the primary key: a replay collides on insert and
-- the handler acks with 200 without repeating the effect. The marker is
-- written in the same transaction as the effect, so a mid-processing failure
-- rolls back both and Stripe's retry still lands.
create table if not exists public.stripe_events (
  id text primary key,
  type text not null default '',
  received_at timestamptz not null default now()
);

alter table public.stripe_events enable row level security;
-- No select policy: this is backend-only bookkeeping. The service role key
-- bypasses RLS; nothing else should read it.
