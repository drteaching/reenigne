-- Per-report metering: an analyses-per-month allowance alongside minutes.
--
-- The analysis credit is charged when a job succeeds, not reserved at
-- enqueue, so a user is only ever billed for a report they received and there
-- is nothing to refund on failure. analysis_jobs.charged_analyses records
-- what was actually charged.
--
-- Idempotent: safe to re-run.

alter table public.profiles
  add column if not exists analyses_used_month integer not null default 0;

alter table public.analysis_jobs
  add column if not exists charged_analyses integer not null default 0;
