-- Important Dates (screens 17-20).
--
-- All-day values stay as dates. Timed values store both the absolute instant and the IANA
-- time-zone name used to interpret annual recurrences. Annual February 29 events are projected
-- onto February 28 in non-leap years by the API.

create table family_event (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references family(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  title text not null check (char_length(btrim(title)) between 1 and 120),
  category text not null check (category in
    ('birthday', 'anniversary', 'family_function', 'cultural_function', 'other')),
  event_date date not null,
  event_at timestamptz,
  time_zone text,
  description text check (description is null or char_length(description) <= 1000),
  repeats_annually boolean not null default false,
  idempotency_key text check
    (idempotency_key is null or char_length(idempotency_key) between 1 and 128),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, family_id),
  check ((event_at is null) = (time_zone is null)),
  check (time_zone is null or char_length(time_zone) between 1 and 64),
  check (event_at is null or (event_at at time zone time_zone)::date = event_date),
  check (category != 'cultural_function' or not repeats_annually)
);

-- The composite key lets the association enforce that an event and related person belong to
-- the same family, even for backend/service-role writes that bypass RLS.
alter table person add constraint person_id_family_unique unique (id, family_id);

create table family_event_person (
  event_id uuid not null,
  family_id uuid not null references family(id) on delete cascade,
  person_id uuid not null,
  primary key (event_id, person_id),
  foreign key (event_id, family_id)
    references family_event(id, family_id) on delete cascade,
  foreign key (person_id, family_id)
    references person(id, family_id) on delete cascade
);

create index family_event_range_idx on family_event (family_id, event_date, id);
create index family_event_annual_idx on family_event (family_id, event_date)
  where repeats_annually;
create index family_event_creator_idx on family_event (created_by, family_id);
create unique index family_event_idempotency_idx on family_event (created_by, idempotency_key)
  where idempotency_key is not null;
create index family_event_person_family_idx on family_event_person (family_id, person_id);

alter table family_event enable row level security;
alter table family_event_person enable row level security;

revoke all on table family_event, family_event_person from anon, authenticated;
grant select on table family_event, family_event_person to authenticated;

create policy "members read" on family_event for select to authenticated
  using (private.is_member(family_id));
create policy "members read" on family_event_person for select to authenticated
  using (private.is_member(family_id));
