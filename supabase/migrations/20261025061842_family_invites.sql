-- Family invitations (screens 22–23): a member proposes that the owner of an email joins the
-- family as a relative of one person in the tree. Accepting adds the member row, the person
-- (or reuses theirs) and one relationship edge, all in one transaction in the API.
--
-- kind is the recipient relative to the anchor: 'parent' means the recipient is the anchor's
-- parent. The API maps it onto relationship's "a is <kind> of b" edges; 'child' becomes
-- (anchor, recipient, 'parent').

create table family_invite (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references family(id) on delete cascade,
  inviter_user_id uuid not null references auth.users(id) on delete cascade,
  anchor_person_id uuid not null references person(id) on delete cascade,
  kind text not null check (kind in ('parent', 'child', 'spouse', 'sibling')),
  email text not null check (email = lower(email) and position('@' in email) > 1),
  status text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  accepted_user_id uuid references auth.users(id) on delete set null,
  person_id uuid references person(id) on delete set null,
  created_at timestamptz not null default now(),
  responded_at timestamptz,
  check ((status = 'pending') = (responded_at is null))
);
create unique index family_invite_one_pending on family_invite (family_id, email)
  where status = 'pending';
create index on family_invite (email, status);

-- Recipients read their invitation through the API, which checks the verified email.
alter table family_invite enable row level security;
grant select on family_invite to authenticated;
create policy "members read" on family_invite for select to authenticated
  using (private.is_member(family_id));
