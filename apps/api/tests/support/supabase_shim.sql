-- Minimal stand-ins for the Supabase-managed objects the migrations depend
-- on, so supabase/migrations/*.sql can be applied to a bare Postgres in CI.
--
-- Without this the migrations cannot run outside Supabase, and the test
-- schema would have to be built from the models instead — which would make
-- the suite structurally incapable of catching model/migration divergence,
-- the exact defect this setup exists to prevent.

create extension if not exists "pgcrypto";

create schema if not exists auth;

-- Supabase's real auth.users has many more columns; only the identity the
-- migrations reference matters here.
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique
);

-- Used by the RLS policies. Returns NULL here; tests connect as a superuser,
-- which bypasses RLS, so policy evaluation is not exercised.
create or replace function auth.uid()
returns uuid
language sql
stable
as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
