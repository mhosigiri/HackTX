-- Notifications and persisted profile preferences (workflow screens 34-35).
-- This follows family memories because memory notifications reference that table.

alter table profile
  add column preferred_language text not null default 'en'
    check (preferred_language in ('en', 'es', 'hi')),
  add column ui_mode_overridden boolean not null default false;

-- A mode that disagrees with the age-derived default was necessarily selected manually.
update profile set ui_mode_overridden = true
where age is not null and ui_mode <> case
  when age < 18 then 'regular'
  when age <= 50 then 'simplified'
  else 'extra_simple'
end;

-- Profiles hold private account settings. Family-facing names and avatars already live on person.
drop policy "self or family read" on profile;
create policy "self reads" on profile for select to authenticated
  using (user_id = (select auth.uid()));

alter table notification drop constraint notification_type_check;
alter table notification alter column recipient_id drop not null;
alter table notification
  add column recipient_user_id uuid references auth.users(id) on delete cascade,
  add column invite_id uuid references family_invite(id) on delete cascade,
  add column memory_id uuid references family_memory(id) on delete cascade,
  add constraint notification_type_check check (type in (
    'request_received', 'request_declined', 'story_ready', 'memory_added',
    'invite_received', 'invite_accepted', 'invite_declined', 'storytime_ready'
  )),
  add constraint notification_one_recipient check (
    num_nonnulls(recipient_id, recipient_user_id) = 1
  );

create index notification_person_inbox_idx
  on notification (recipient_id, created_at desc, id desc);
create index notification_user_inbox_idx
  on notification (recipient_user_id, created_at desc, id desc);
create index family_memory_timeline_idx
  on family_memory (family_id, event_date, id)
  where status = 'published' and event_date is not null;

-- Deterministic action references make notification delivery safe to retry.
create unique index notification_request_once_idx
  on notification (recipient_id, type, request_id)
  where request_id is not null;
create unique index notification_person_invite_once_idx
  on notification (recipient_id, type, invite_id)
  where invite_id is not null and recipient_id is not null;
create unique index notification_user_invite_once_idx
  on notification (recipient_user_id, type, invite_id)
  where invite_id is not null and recipient_user_id is not null;
create unique index notification_memory_once_idx
  on notification (recipient_id, type, memory_id)
  where memory_id is not null;

drop policy "recipient reads" on notification;
create function private.can_read_notification(nid uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.notification n
    where n.id = nid and
    (
      n.recipient_user_id = (select auth.uid())
      or exists (
        select 1 from public.member m
        where m.person_id = n.recipient_id
          and m.user_id = (select auth.uid())
      )
    )
    and case
      when n.type = 'memory_added' then
        exists (
          select 1 from public.family_memory fm
          join public.member m on m.family_id = fm.family_id
          where fm.id = n.memory_id and fm.status = 'published'
            and m.user_id = (select auth.uid())
        )
      when n.type = 'story_ready' then
        exists (
          select 1 from public.story s
          join public.heirloom h on h.id = s.heirloom_id
          join public.member m on m.family_id = h.family_id
          where s.id = n.story_id and s.status = 'published'
            and m.user_id = (select auth.uid())
        )
      -- Protected Storytime already publishes recipient-scoped notifications but has no
      -- supporting-backend destination contract. Preserve its existing recipient-only RLS.
      when n.type = 'storytime_ready' then true
      when n.type = 'request_received' then
        exists (
          select 1 from public.story_request r
          join public.heirloom h on h.id = r.heirloom_id
          join public.member m on m.family_id = h.family_id
          where r.id = n.request_id
            and r.storyteller_id = n.recipient_id
            and m.user_id = (select auth.uid())
        )
      when n.type = 'request_declined' then
        exists (
          select 1 from public.story_request r
          join public.heirloom h on h.id = r.heirloom_id
          join public.member m on m.family_id = h.family_id
          where r.id = n.request_id and r.listener_id = n.recipient_id
            and m.user_id = (select auth.uid())
        )
      when n.type = 'invite_received' then
        exists (
          select 1 from public.family_invite fi
          join auth.users u on u.id = (select auth.uid())
          where fi.id = n.invite_id and fi.email = lower(u.email)
            and u.email_confirmed_at is not null
        )
      else exists (
        select 1 from public.family_invite fi
        where fi.id = n.invite_id
          and fi.inviter_user_id = (select auth.uid())
      )
    end
  );
$$;
revoke all on function private.can_read_notification(uuid) from public;
grant execute on function private.can_read_notification(uuid) to authenticated;

create policy "recipient reads" on notification for select to authenticated
  using (private.can_read_notification(id));
