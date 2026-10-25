-- Family Availability and private schedules (screens 29-32).
--
-- Schedule rows and settings are private to their owning account. Relatives receive only a
-- current derived status through FastAPI; there is intentionally no public status table or view.

create table availability_setting (
  user_id uuid primary key references auth.users(id) on delete cascade,
  sharing_enabled boolean not null default false,
  schedule_configured boolean not null default false,
  time_zone text not null default 'UTC'
    check (char_length(time_zone) between 1 and 64),
  override_status text check (override_status in ('free', 'busy')),
  override_expires_at timestamptz,
  updated_at timestamptz not null default now(),
  check ((override_status is null) = (override_expires_at is null))
);

create table private_schedule_entry (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  private_label text check
    (private_label is null or char_length(btrim(private_label)) between 1 and 80),
  start_date date not null,
  start_time time not null,
  end_time time not null,
  time_zone text not null check (char_length(time_zone) between 1 and 64),
  repeat_weekdays smallint[] not null default '{}'
    check (cardinality(repeat_weekdays) <= 7 and repeat_weekdays <@ array[0,1,2,3,4,5,6]::smallint[]),
  repeat_until date,
  idempotency_key text check
    (idempotency_key is null or char_length(idempotency_key) between 1 and 128),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (start_time != end_time),
  check ((cardinality(repeat_weekdays) = 0) = (repeat_until is null)),
  check (repeat_until is null or repeat_until between start_date and start_date + 366)
);

create index private_schedule_owner_idx on private_schedule_entry (user_id, start_date, id);
create unique index private_schedule_idempotency_idx
  on private_schedule_entry (user_id, idempotency_key)
  where idempotency_key is not null;

alter table availability_setting enable row level security;
alter table private_schedule_entry enable row level security;

revoke all on table availability_setting, private_schedule_entry from anon, authenticated;
grant select on table availability_setting, private_schedule_entry to authenticated;

create policy "owners read" on availability_setting for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "owners read" on private_schedule_entry for select to authenticated
  using ((select auth.uid()) = user_id);
