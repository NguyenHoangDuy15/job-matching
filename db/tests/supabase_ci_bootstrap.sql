-- =============================================================================
-- Intelligent Job Matching & Market Analytics
-- File: supabase_ci_bootstrap.sql
-- Purpose: Minimal Supabase Auth & Storage mock layer for running schema.sql,
--          seed_reference_data.sql, and rls_test.sql inside a standalone
--          pgvector/pgvector:pg16 container in GitHub Actions CI.
--          Safe (idempotent) to skip when running against Supabase CLI / Cloud.
-- =============================================================================

begin;

-- 1. Roles used by Supabase PostgREST & Storage
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    create role supabase_auth_admin nologin noinherit;
  end if;
end $$;

-- 1b. Schema "extensions": Supabase có sẵn; migration 0001 cài vector/pg_trgm/unaccent/citext vào đây.
create schema if not exists extensions;
grant usage on schema extensions to anon, authenticated, service_role;

-- 2. Minimal auth schema (if not running inside full Supabase stack)
create schema if not exists auth;
grant usage on schema auth to anon, authenticated, service_role, supabase_auth_admin;

create table if not exists auth.users (
  id                  uuid primary key,
  email               text,
  encrypted_password  text,
  email_confirmed_at  timestamptz,
  raw_app_meta_data   jsonb default '{}'::jsonb,
  raw_user_meta_data  jsonb default '{}'::jsonb,
  last_sign_in_at     timestamptz,
  created_at          timestamptz default now(),
  updated_at          timestamptz default now()
);

create table if not exists auth.sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  not_after   timestamptz
);

create or replace function auth.uid()
returns uuid
language sql stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid;
$$;

create or replace function auth.jwt()
returns jsonb
language sql stable
as $$
  select coalesce(
    nullif(current_setting('request.jwt.claims', true), '')::jsonb,
    '{}'::jsonb
  );
$$;

grant execute on function auth.uid() to anon, authenticated, service_role, supabase_auth_admin;
grant execute on function auth.jwt() to anon, authenticated, service_role, supabase_auth_admin;

-- 3. Minimal storage schema (if not running inside full Supabase stack)
create schema if not exists storage;
grant usage on schema storage to anon, authenticated, service_role;

create table if not exists storage.buckets (
  id                  text primary key,
  name                text not null,
  public              boolean not null default false,
  file_size_limit     bigint,
  allowed_mime_types  text[],
  created_at          timestamptz default now(),
  updated_at          timestamptz default now()
);

create table if not exists storage.objects (
  id          uuid primary key default gen_random_uuid(),
  bucket_id   text references storage.buckets(id),
  name        text,
  owner       uuid default auth.uid(),
  created_at  timestamptz default now(),
  updated_at  timestamptz default now(),
  metadata    jsonb
);

alter table storage.objects enable row level security;

create or replace function storage.foldername(name text)
returns text[]
language sql immutable
as $$
  select string_to_array(name, '/');
$$;

grant execute on function storage.foldername(text) to anon, authenticated, service_role;
grant select, insert, update, delete on storage.objects to anon, authenticated, service_role;

commit;

