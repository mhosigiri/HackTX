"""Family invitations (screens 22–23).

A member invites an email to join as a relative of one person in the tree. `kind` is the
recipient relative to the anchor: 'parent' means the recipient is the anchor's parent.
Nothing is emailed; the inviter shares the link. Only the account whose verified email matches
can accept or decline, and only an accepted invitation adds membership and a relationship.

The API's database role bypasses RLS, so every route here checks family membership or the
recipient's identity itself.
"""

from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser, User, require_member
from app.db import pool
from app.routers.notifications import create_notification

router = APIRouter(prefix="/api", tags=["invites"])

Kind = Literal["parent", "child", "spouse", "sibling"]


class CreateInvite(BaseModel):
    anchor_person_id: UUID
    kind: Kind
    email: str


class Invite(BaseModel):
    id: UUID
    family_id: UUID
    family_name: str
    anchor_person_id: UUID
    anchor_name: str
    kind: Kind
    email: str
    status: Literal["pending", "accepted", "declined"]
    inviter_name: str | None = None
    person_id: UUID | None = None
    created_at: str
    responded_at: str | None = None
    # True only for the intended recipient while the invitation is still pending.
    can_respond: bool = False


_SELECT = """
    select i.id, i.family_id, f.name as family_name, i.anchor_person_id,
           ap.display_name as anchor_name, i.kind, i.email, i.status,
           ip.display_name as inviter_name, i.person_id,
           i.created_at::text, i.responded_at::text
    from family_invite i
    join family f on f.id = i.family_id
    join person ap on ap.id = i.anchor_person_id
    left join member im on im.user_id = i.inviter_user_id and im.family_id = i.family_id
    left join person ip on ip.id = im.person_id
"""


def _invite(row: asyncpg.Record, can_respond: bool = False) -> Invite:
    return Invite(**row, can_respond=can_respond)


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    local, _, domain = email.partition("@")
    if (
        not local
        or "@" in domain
        or "." not in domain.strip(".")
        or any(c.isspace() for c in email)
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "add a valid email address")
    return email


def edge(kind: str, anchor: UUID, recipient: UUID) -> tuple[UUID, UUID, str]:
    """Maps an invitation onto relationship's "a is <kind> of b" representation."""
    if kind == "child":
        return anchor, recipient, "parent"
    return recipient, anchor, kind


async def verified_email(conn: asyncpg.Connection, user: User) -> str | None:
    """The account's email as Supabase Auth confirmed it. Never trust an email from the client."""
    row = await conn.fetchrow(
        "select email, email_confirmed_at from auth.users where id = $1", user.id
    )
    if row is None or not row["email"] or row["email_confirmed_at"] is None:
        return None
    return row["email"].lower()


async def require_recipient(conn: asyncpg.Connection, user: User, invite_email: str) -> None:
    email = await verified_email(conn, user)
    if email is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "confirm your email address first")
    if email != invite_email:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "this invitation was sent to a different email address"
        )


async def check_tree_rules(
    conn: asyncpg.Connection, anchor: UUID, recipient: UUID | None, kind: str
) -> None:
    """Rejects edges the tree can't hold. `recipient` is None when they have no person yet."""
    if recipient is not None:
        if recipient == anchor:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "someone can't be their own relative")
        linked = await conn.fetchval(
            "select 1 from relationship where (a = $1 and b = $2) or (a = $2 and b = $1)",
            anchor,
            recipient,
        )
        if linked:
            raise HTTPException(status.HTTP_409_CONFLICT, "they are already connected in the tree")
    if kind not in ("parent", "child"):
        return
    parent, child = (recipient, anchor) if kind == "parent" else (anchor, recipient)
    if child is not None:
        parents = await conn.fetchval(
            "select count(*) from relationship where b = $1 and kind = 'parent'", child
        )
        if parents >= 2:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "that person already has two parents in the tree"
            )
    if parent is not None and child is not None:
        loop = await conn.fetchval(
            """
            with recursive down(id) as (
              select b from relationship where a = $1 and kind = 'parent'
              union
              select r.b from relationship r join down d on r.a = d.id where r.kind = 'parent'
            )
            select 1 from down where id = $2
            """,
            child,
            parent,
        )
        if loop:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "that would make someone their own ancestor"
            )


@router.post("/families/{family_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(family_id: UUID, body: CreateInvite, user: CurrentUser) -> Invite:
    email = normalize_email(body.email)
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        anchor_family = await conn.fetchval(
            "select family_id from person where id = $1", body.anchor_person_id
        )
        if anchor_family != family_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "that person is not in this family")
        own = await conn.fetchval("select lower(email) from auth.users where id = $1", user.id)
        if own == email:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "you can't invite yourself")
        existing = await conn.fetchval(
            "select m.person_id from auth.users u join member m on m.user_id = u.id "
            "where lower(u.email) = $1 and m.family_id = $2",
            email,
            family_id,
        )
        await check_tree_rules(conn, body.anchor_person_id, existing, body.kind)
        try:
            invite_id = await conn.fetchval(
                "insert into family_invite (family_id, inviter_user_id, anchor_person_id, kind, "
                "email) values ($1, $2, $3, $4, $5) returning id",
                family_id,
                user.id,
                body.anchor_person_id,
                body.kind,
                email,
            )
        except asyncpg.UniqueViolationError as e:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "that email already has a pending invitation"
            ) from e
        recipient_user_id = await conn.fetchval(
            "select id from auth.users where lower(email) = $1 and email_confirmed_at is not null",
            email,
        )
        if recipient_user_id is not None:
            await create_notification(
                conn,
                ntype="invite_received",
                recipient_user_id=recipient_user_id,
                invite_id=invite_id,
            )
        return _invite(await conn.fetchrow(_SELECT + " where i.id = $1", invite_id))


@router.get("/families/{family_id}/invites")
async def list_invites(family_id: UUID, user: CurrentUser) -> list[Invite]:
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        rows = await conn.fetch(
            _SELECT
            + " where i.family_id = $1 order by (i.status = 'pending') desc, i.created_at desc",
            family_id,
        )
    return [_invite(r) for r in rows]


@router.get("/invites/{invite_id}")
async def get_invite(invite_id: UUID, user: CurrentUser) -> Invite:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(_SELECT + " where i.id = $1", invite_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found")
        is_recipient = await verified_email(conn, user) == row["email"]
        if not is_recipient:
            member = await conn.fetchval(
                "select 1 from member where user_id = $1 and family_id = $2",
                user.id,
                row["family_id"],
            )
            if not member:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "this invitation was sent to a different email address",
                )
    return _invite(row, can_respond=is_recipient and row["status"] == "pending")


async def _join(conn: asyncpg.Connection, user: User, family_id: UUID, email: str) -> UUID:
    """The recipient's person in the family. Someone already in the family keeps their person;
    anyone else gets a member row and a new person. Membership in other families is untouched."""
    await conn.execute(
        "select pg_advisory_xact_lock(hashtextextended($1::uuid::text || $2::uuid::text, 0))",
        user.id,
        family_id,
    )
    row = await conn.fetchrow(
        "select person_id from member where user_id = $1 and family_id = $2", user.id, family_id
    )
    if row and row["person_id"]:
        return row["person_id"]
    name = await conn.fetchval("select display_name from profile where user_id = $1", user.id)
    person_id = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, $2) returning id",
        family_id,
        (name or "").strip() or email.split("@")[0],
    )
    if row:
        await conn.execute(
            "update member set person_id = $3 where user_id = $1 and family_id = $2",
            user.id,
            family_id,
            person_id,
        )
    else:
        await conn.execute(
            "insert into member (user_id, family_id, person_id) values ($1, $2, $3)",
            user.id,
            family_id,
            person_id,
        )
    return person_id


@router.post("/invites/{invite_id}/accept")
async def accept_invite(invite_id: UUID, user: CurrentUser) -> Invite:
    async with pool().acquire() as conn:
        async with conn.transaction():
            # The row lock serializes double taps and concurrent accepts of one invitation.
            inv = await conn.fetchrow(
                "select * from family_invite where id = $1 for update", invite_id
            )
            if inv is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found")
            await require_recipient(conn, user, inv["email"])
            if inv["status"] == "declined":
                raise HTTPException(status.HTTP_409_CONFLICT, "this invitation was declined")
            if inv["status"] == "accepted" and inv["accepted_user_id"] != user.id:
                raise HTTPException(status.HTTP_409_CONFLICT, "this invitation was already used")
            if inv["status"] == "pending":
                person_id = await _join(conn, user, inv["family_id"], inv["email"])
                # Locks the anchor so two accepts can't both give it a third parent.
                await conn.execute(
                    "select 1 from person where id = $1 for update", inv["anchor_person_id"]
                )
                await check_tree_rules(conn, inv["anchor_person_id"], person_id, inv["kind"])
                a, b, kind = edge(inv["kind"], inv["anchor_person_id"], person_id)
                await conn.execute(
                    "insert into relationship (family_id, a, b, kind) values ($1, $2, $3, $4)",
                    inv["family_id"],
                    a,
                    b,
                    kind,
                )
                await conn.execute(
                    "update family_invite set status = 'accepted', accepted_user_id = $2, "
                    "person_id = $3, responded_at = now() where id = $1",
                    invite_id,
                    user.id,
                    person_id,
                )
            inviter_id = await conn.fetchval(
                "select person_id from member where user_id = $1 and family_id = $2",
                inv["inviter_user_id"],
                inv["family_id"],
            )
            if inviter_id is not None:
                await create_notification(
                    conn,
                    ntype="invite_accepted",
                    recipient_id=inviter_id,
                    invite_id=invite_id,
                )
        return _invite(await conn.fetchrow(_SELECT + " where i.id = $1", invite_id))


@router.post("/invites/{invite_id}/decline")
async def decline_invite(invite_id: UUID, user: CurrentUser) -> Invite:
    async with pool().acquire() as conn:
        async with conn.transaction():
            inv = await conn.fetchrow(
                "select email, status, inviter_user_id, family_id "
                "from family_invite where id = $1 for update",
                invite_id,
            )
            if inv is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found")
            await require_recipient(conn, user, inv["email"])
            if inv["status"] == "accepted":
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "this invitation was already accepted"
                )
            if inv["status"] == "pending":
                await conn.execute(
                    "update family_invite set status = 'declined', responded_at = now() "
                    "where id = $1",
                    invite_id,
                )
            inviter_id = await conn.fetchval(
                "select person_id from member where user_id = $1 and family_id = $2",
                inv["inviter_user_id"],
                inv["family_id"],
            )
            if inviter_id is not None:
                await create_notification(
                    conn,
                    ntype="invite_declined",
                    recipient_id=inviter_id,
                    invite_id=invite_id,
                )
        return _invite(await conn.fetchrow(_SELECT + " where i.id = $1", invite_id))
