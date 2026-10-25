-- Account-to-account connections. Each side keeps its own label, so Jimmy can call Jaeden a
-- friend while Jaeden calls Jimmy family. A connection exists only between two real accounts.

create table connection_request (
  id uuid primary key default gen_random_uuid(),
  from_user uuid not null references auth.users(id) on delete cascade,
  to_user uuid not null references auth.users(id) on delete cascade,
  -- How from_user will see to_user once accepted.
  kind text not null check (kind in ('family', 'friend')),
  status text not null default 'pending' check (status in ('pending', 'accepted', 'declined')),
  created_at timestamptz not null default now(),
  responded_at timestamptz,
  check (from_user != to_user)
);
-- One open request per pair, whichever way it was sent.
create unique index connection_request_one_open on connection_request
  (least(from_user, to_user), greatest(from_user, to_user)) where status = 'pending';
create index on connection_request (to_user, status);

-- One row per viewer: user_id sees other_id as kind.
create table connection (
  user_id uuid not null references auth.users(id) on delete cascade,
  other_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('family', 'friend')),
  created_at timestamptz not null default now(),
  primary key (user_id, other_id),
  check (user_id != other_id)
);

alter table connection_request enable row level security;
alter table connection enable row level security;
grant select on connection_request, connection to authenticated;

create policy "own requests" on connection_request for select to authenticated
  using ((select auth.uid()) in (from_user, to_user));
create policy "own connections" on connection for select to authenticated
  using (user_id = (select auth.uid()));
