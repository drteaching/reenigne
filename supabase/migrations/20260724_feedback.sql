-- User feedback intake.
--
-- Bug reports and improvement suggestions from the desktop app, the CLI and
-- the public website. A separate triage job classifies each row and may file
-- a GitHub issue; see docs/feedback-pipeline.md.
--
-- Nothing here is billable: feedback never touches quota, credits or any
-- other billing state.
--
-- Idempotent: safe to re-run.

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),

  -- PRIVACY: nullable, and ON DELETE SET NULL rather than CASCADE.
  --
  -- Deleting an account therefore anonymises that person's feedback rather
  -- than removing it: the report, its title, description and context survive
  -- with no link back to a user. This is deliberate — a filed GitHub issue
  -- would outlive the row anyway, so deleting the row would leave the issue
  -- orphaned rather than actually erasing anything.
  --
  -- The privacy policy must state this plainly: "feedback you submit is
  -- retained after account deletion, with your identity removed". If that is
  -- ever unacceptable, the change is ON DELETE CASCADE here plus a process
  -- for closing the corresponding issues.
  --
  -- Null also covers the legitimate case: anonymous submissions from the
  -- public site, which never had a user.
  user_id uuid references public.profiles (id) on delete set null,

  kind text not null default 'bug',
  title text not null default '',
  description text not null default '',
  context_json text,

  status text not null default 'received',
  triage_json text,
  github_issue_url text,

  -- HMAC of the submitter's IP, never the address itself. Enough to rate
  -- limit anonymous submissions per source, not enough to be a location log.
  -- Keyed by API_SECRET_KEY, so rotating that key resets anonymous windows.
  submitter_ip_hash text,

  created_at timestamptz not null default now(),

  constraint feedback_kind_check check (kind in ('bug', 'improvement')),
  constraint feedback_status_check
    check (status in ('received', 'triaged', 'filed', 'dismissed'))
);

-- Rate-limit lookups: recent rows for one user, or for one hashed source.
create index if not exists feedback_user_created_idx
  on public.feedback (user_id, created_at desc);
create index if not exists feedback_ip_created_idx
  on public.feedback (submitter_ip_hash, created_at desc);

-- The triage queue claims by status and age.
create index if not exists feedback_status_created_idx
  on public.feedback (status, created_at);

alter table public.feedback enable row level security;

-- Users may read back their own submissions. Anonymous rows (user_id null)
-- are readable by nobody through the API; the backend uses the service role
-- key, which bypasses RLS.
create policy "feedback_select_own"
  on public.feedback for select
  using (auth.uid() = user_id);
