-- reenigne profiles (linked to Supabase Auth)
-- Run via Supabase SQL editor or: supabase db push

create extension if not exists "pgcrypto";

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text unique not null,
  password_hash text, -- unused with Supabase Auth; kept for local/dev parity
  created_at timestamptz not null default now(),
  stripe_customer_id text,
  subscription_status text not null default 'none',
  subscription_id text,
  plan text not null default 'free',
  minutes_used_month double precision not null default 0,
  usage_month text not null default ''
);

create index if not exists profiles_email_idx on public.profiles (email);
create index if not exists profiles_stripe_customer_idx on public.profiles (stripe_customer_id);

alter table public.profiles enable row level security;

-- Users can read their own profile
create policy "profiles_select_own"
  on public.profiles for select
  using (auth.uid() = id);

-- Service role / backend uses service key (bypasses RLS)

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, usage_month)
  values (
    new.id,
    lower(new.email),
    to_char(timezone('utc', now()), 'YYYY-MM')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
