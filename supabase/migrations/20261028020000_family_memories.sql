-- Family Memories (workflow screens 24-28).
-- Reuses the existing private media buckets/table. AI-generated stories and heirloom
-- memory_note rows remain separate and unchanged.

create table family_memory (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references family(id) on delete cascade,
  contributor_id uuid not null,
  created_by uuid not null references auth.users(id) on delete cascade,
  title text,
  description text,
  event_date date,
  language text not null default 'en',
  status text not null default 'draft' check (status in ('draft', 'published')),
  cover_media_id uuid,
  recording_media_id uuid,
  idempotency_key text,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (title is null or (char_length(btrim(title)) between 1 and 120)),
  check (description is null or char_length(description) <= 500),
  check (char_length(language) between 2 and 32),
  check (
    status = 'draft'
    or (
      title is not null and cover_media_id is not null and recording_media_id is not null
      and published_at is not null
    )
  )
);
create index family_memory_family_published_idx
  on family_memory (family_id, published_at desc, id desc)
  where status = 'published';
create index family_memory_owner_draft_idx
  on family_memory (created_by, updated_at desc, id desc)
  where status = 'draft';
create unique index family_memory_idempotency_idx
  on family_memory (created_by, idempotency_key)
  where idempotency_key is not null;

alter table family_memory add constraint family_memory_contributor_family_fk
  foreign key (contributor_id, family_id) references person (id, family_id) on delete restrict;

alter table media
  add column memory_id uuid references family_memory(id) on delete cascade,
  add column byte_size bigint check (byte_size is null or byte_size > 0);
create index media_memory_idx on media (memory_id, created_at);

create table family_memory_photo (
  memory_id uuid not null references family_memory(id) on delete cascade,
  media_id uuid not null references media(id) on delete restrict,
  position smallint not null check (position between 0 and 32767),
  primary key (memory_id, media_id),
  unique (memory_id, position)
);

alter table family_memory
  add constraint family_memory_cover_fk
    foreign key (cover_media_id) references media(id) on delete restrict,
  add constraint family_memory_recording_fk
    foreign key (recording_media_id) references media(id) on delete restrict;

-- Backend writes use the service role. Browser access remains read-only and RLS-limited.
alter table family_memory enable row level security;
alter table family_memory_photo enable row level security;

create function private.can_read_family_memory(mid uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.family_memory fm
    where fm.id = mid
      and (
        fm.created_by = (select auth.uid())
        or (fm.status = 'published' and private.is_member(fm.family_id))
      )
  );
$$;

create function private.can_read_media(mid uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.media m
    left join public.family_memory fm on fm.id = m.memory_id
    where m.id = mid
      and (
        (m.memory_id is null and private.is_member(m.family_id))
        or (
          m.memory_id is not null
          and (
            fm.created_by = (select auth.uid())
            or (
              fm.status = 'published'
              and m.upload_status = 'ready'
              and private.is_member(fm.family_id)
              and (
                fm.recording_media_id = m.id
                or exists (
                  select 1 from public.family_memory_photo mp
                  where mp.memory_id = fm.id and mp.media_id = m.id
                )
              )
            )
          )
        )
      )
  );
$$;

create function private.can_read_storage_object(object_path text) returns boolean
language sql stable security definer set search_path = '' as $$
  select case
    when exists (select 1 from public.media m where m.storage_path = object_path)
      then exists (
        select 1 from public.media m
        where m.storage_path = object_path and private.can_read_media(m.id)
      )
    else false
  end;
$$;

revoke all on function private.can_read_family_memory(uuid) from public;
revoke all on function private.can_read_media(uuid) from public;
revoke all on function private.can_read_storage_object(text) from public;
grant execute on function private.can_read_family_memory(uuid) to authenticated;
grant execute on function private.can_read_media(uuid) to authenticated;
grant execute on function private.can_read_storage_object(text) to authenticated;

create policy "owner or family reads" on family_memory for select to authenticated
  using (private.can_read_family_memory(id));
create policy "owner or family reads" on family_memory_photo for select to authenticated
  using (private.can_read_family_memory(memory_id));

drop policy "members read" on media;
create policy "authorized media reads" on media for select to authenticated
  using (private.can_read_media(id));

drop policy "members read family objects" on storage.objects;
create policy "authorized family objects read" on storage.objects for select to authenticated
  using (
    bucket_id in ('photos', 'audio', 'generated')
    and private.can_read_storage_object(name)
  );

revoke all on family_memory, family_memory_photo from anon, authenticated;
grant select on family_memory, family_memory_photo to authenticated;

alter publication supabase_realtime add table family_memory;
