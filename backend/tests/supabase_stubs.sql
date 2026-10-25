-- Minimal stand-ins for the Supabase-managed schemas the migration depends on.
create schema auth;
create table auth.users (id uuid primary key, email text, email_confirmed_at timestamptz);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
create role authenticated;
create role anon;
grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;

create schema storage;
create table storage.buckets (id text primary key, name text, public boolean);
create table storage.objects (
  id uuid primary key default gen_random_uuid(), bucket_id text, name text
);
create function storage.foldername(name text) returns text[] language sql as $$
  select string_to_array(name, '/')
$$;
alter table storage.objects enable row level security;
grant usage on schema storage to authenticated;
grant select on storage.objects to authenticated;

create publication supabase_realtime;
