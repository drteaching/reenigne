-- Record which usage period a job's quota debit belongs to.
--
-- Minutes are debited at enqueue and refunded if the job ultimately fails.
-- reset_usage_if_needed zeroes the counter on month rollover, so a refund is
-- only valid against the same period — otherwise a job enqueued last month
-- would credit minutes that are no longer counted.
--
-- Idempotent: safe to re-run.

alter table public.analysis_jobs
  add column if not exists usage_month text not null default '';
