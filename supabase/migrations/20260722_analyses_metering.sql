-- Per-report metering: an analyses-per-month allowance alongside minutes.
--
-- The credit is charged when a job succeeds, inside the same transaction as
-- the job's terminal update, so a user is only ever billed for a report they
-- received. Nothing is reserved at enqueue and nothing is refunded, so no
-- per-job bookkeeping column is needed — a charged job is simply one whose
-- status is 'succeeded'.
--
-- Enforcement stays exact because the enqueue check counts jobs already
-- queued or running toward the allowance; see app/jobs.py:enqueue_analysis.
--
-- Idempotent: safe to re-run.

alter table public.profiles
  add column if not exists analyses_used_month integer not null default 0;
