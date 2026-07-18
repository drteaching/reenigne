-- Asynchronous analysis jobs.
-- Run via Supabase SQL editor or: supabase db push

create table if not exists public.analysis_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  status text not null default 'queued',

  target text not null default '',
  duration_seconds double precision not null default 0,
  prompt_template text not null default 'teardown',
  model text not null default '',

  -- Frames payload; cleared once the job is terminal.
  request_json text,

  result_markdown text,
  result_features_json text,
  model_used text,
  error text,

  attempts integer not null default 0,
  charged_minutes double precision not null default 0,

  -- Epoch seconds. Kept numeric so lease comparisons behave identically on
  -- Postgres and on SQLite in local/dev runs.
  lease_expires_at double precision not null default 0,
  lock_token uuid,

  created_at timestamptz not null default now(),
  finished_at timestamptz,

  constraint analysis_jobs_status_check
    check (status in ('queued', 'running', 'succeeded', 'failed'))
);

-- The runner's claim query: oldest runnable job first.
create index if not exists analysis_jobs_claim_idx
  on public.analysis_jobs (status, created_at);

-- Per-user listing and the active-job cap.
create index if not exists analysis_jobs_user_idx
  on public.analysis_jobs (user_id, created_at desc);

alter table public.analysis_jobs enable row level security;

-- Users may read only their own jobs. The backend uses the service role key
-- (which bypasses RLS) to claim and update them.
create policy "analysis_jobs_select_own"
  on public.analysis_jobs for select
  using (auth.uid() = user_id);
