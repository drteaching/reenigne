-- Feedback triage queue.
--
-- A second, lightweight job type sharing the claim/lease mechanics in
-- app/queue.py with the analysis queue.
--
-- Deliberately its own table rather than a job_type column on analysis_jobs.
-- That table carries charged_minutes, usage_month and charged_credits — the
-- whole billing surface. Triage must never touch quota, credits or refunds,
-- and giving it a table with no billing columns makes that structural rather
-- than a rule someone has to remember.
--
-- Idempotent: safe to re-run.

create table if not exists public.feedback_triage_jobs (
  id uuid primary key default gen_random_uuid(),
  feedback_id uuid not null references public.feedback (id) on delete cascade,

  status text not null default 'queued',
  attempts integer not null default 0,
  error text,

  -- Epoch seconds, matching analysis_jobs: SQLite returns naive datetimes and
  -- comparing those against tz-aware ones raises.
  lease_expires_at double precision not null default 0,
  lock_token uuid,

  created_at timestamptz not null default now(),
  finished_at timestamptz,

  constraint feedback_triage_status_check
    check (status in ('queued', 'running', 'succeeded', 'failed'))
);

-- The claim query, and the drain's oldest-runnable peek.
create index if not exists feedback_triage_claim_idx
  on public.feedback_triage_jobs (status, created_at);

alter table public.feedback_triage_jobs enable row level security;
-- Backend-only bookkeeping; no select policy. The service role bypasses RLS.
