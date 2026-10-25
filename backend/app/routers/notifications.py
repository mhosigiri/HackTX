"""Recipient-only persisted notifications with retry-safe action references."""

import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser
from app.db import pool

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
log = logging.getLogger("lorebook.notifications")

NotificationType = Literal[
    "request_received",
    "request_declined",
    "story_ready",
    "memory_added",
    "invite_received",
    "invite_accepted",
    "invite_declined",
]
DestinationType = Literal[
    "story_request", "story", "invitation", "invitation_status", "family_tree", "family_memory"
]

MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000


class Notification(BaseModel):
    id: UUID
    type: NotificationType
    message: str
    request_id: UUID | None = None
    story_id: UUID | None = None
    invite_id: UUID | None = None
    memory_id: UUID | None = None
    related_image_media_id: UUID | None = None
    destination_type: DestinationType
    destination_id: UUID
    read_at: datetime | None = None
    created_at: datetime


class UnreadCount(BaseModel):
    count: int


_SELECT = """
    select n.id, n.type, n.request_id, n.story_id, n.invite_id, n.memory_id,
           n.read_at, n.created_at,
           r.listener_id, r.storyteller_id,
           listener.display_name as listener_name,
           teller.display_name as storyteller_name,
           coalesce(request_heirloom.id, story_heirloom.id) as heirloom_id,
           coalesce(request_heirloom.title, story_heirloom.title, 'this object') as heirloom_title,
           coalesce(
             request_heirloom.cover_media_id, story_heirloom.cover_media_id
           ) as object_image_id,
           fi.family_id as invite_family_id, fi.email as invite_email,
           f.name as invite_family_name, inviter.display_name as inviter_name,
           inviter.avatar_media_id as inviter_image_id,
           fm.title as memory_title, fm.cover_media_id as memory_image_id,
           contributor.display_name as contributor_name
    from notification n
    left join story_request r on r.id = n.request_id
    left join person listener on listener.id = r.listener_id
    left join person teller on teller.id = r.storyteller_id
    left join heirloom request_heirloom on request_heirloom.id = r.heirloom_id
    left join story s on s.id = n.story_id
    left join heirloom story_heirloom on story_heirloom.id = s.heirloom_id
    left join family_invite fi on fi.id = n.invite_id
    left join family f on f.id = fi.family_id
    left join member inviter_member
      on inviter_member.user_id = fi.inviter_user_id and inviter_member.family_id = fi.family_id
    left join person inviter on inviter.id = inviter_member.person_id
    left join family_memory fm on fm.id = n.memory_id and fm.status = 'published'
    left join person contributor on contributor.id = fm.contributor_id
"""


async def create_notification(
    conn: asyncpg.Connection,
    *,
    ntype: NotificationType,
    recipient_id: UUID | None = None,
    recipient_user_id: UUID | None = None,
    request_id: UUID | None = None,
    story_id: UUID | None = None,
    invite_id: UUID | None = None,
    memory_id: UUID | None = None,
) -> bool:
    """Attempt delivery in a savepoint so failure never rolls back the saved action.

    A retry of the action may call this again; partial unique indexes make that safe.
    """
    if (recipient_id is None) == (recipient_user_id is None):
        raise ValueError("provide exactly one notification recipient")
    try:
        async with conn.transaction():
            result = await conn.execute(
                """
                insert into notification
                  (recipient_id, recipient_user_id, type, request_id, story_id,
                   invite_id, memory_id)
                values ($1, $2, $3, $4, $5, $6, $7)
                on conflict do nothing
                """,
                recipient_id,
                recipient_user_id,
                ntype,
                request_id,
                story_id,
                invite_id,
                memory_id,
            )
        return result == "INSERT 0 1"
    except asyncpg.PostgresError as exc:
        # Keep delivery failure observable without logging row values, recipient identifiers,
        # private messages, or database error details that may contain them.
        log.error(
            "notification delivery failed for type=%s error_class=%s",
            ntype,
            type(exc).__name__,
        )
        return False


async def _sync_pending_invites(conn: asyncpg.Connection, user_id: UUID) -> None:
    """Materialize invitations sent before the recipient created or confirmed an account."""
    row = await conn.fetchrow(
        "select lower(email) as email from auth.users "
        "where id = $1 and email_confirmed_at is not null",
        user_id,
    )
    if row is None or not row["email"]:
        return
    invites = await conn.fetch(
        "select id from family_invite where email = $1 and status = 'pending'", row["email"]
    )
    for invite in invites:
        await create_notification(
            conn,
            ntype="invite_received",
            recipient_user_id=user_id,
            invite_id=invite["id"],
        )


def _notification(row: asyncpg.Record) -> Notification:
    ntype = row["type"]
    image_id = None
    if ntype == "request_received":
        sender = row["listener_name"] or "A family member"
        message = f"{sender} wants to hear about {row['heirloom_title']}."
        destination_type, destination_id = "story_request", row["request_id"]
        image_id = row["object_image_id"]
    elif ntype == "request_declined":
        message = f"{row['storyteller_name'] or 'Your relative'} could not tell this story."
        destination_type, destination_id = "story_request", row["request_id"]
        image_id = row["object_image_id"]
    elif ntype == "story_ready":
        message = f"The story about {row['heirloom_title']} is ready."
        destination_type, destination_id = "story", row["heirloom_id"]
        image_id = row["object_image_id"]
    elif ntype == "invite_received":
        message = (
            f"{row['inviter_name'] or 'A family member'} invited you to "
            f"{row['invite_family_name'] or 'their family'}."
        )
        destination_type, destination_id = "invitation", row["invite_id"]
        image_id = row["inviter_image_id"]
    elif ntype == "invite_accepted":
        message = f"{row['invite_email']} accepted your family invitation."
        destination_type, destination_id = "family_tree", row["invite_family_id"]
    elif ntype == "invite_declined":
        message = f"{row['invite_email']} declined your family invitation."
        destination_type, destination_id = "invitation_status", row["invite_id"]
    else:
        message = (
            f"{row['contributor_name'] or 'A family member'} shared "
            f"{row['memory_title'] or 'a family memory'}."
        )
        destination_type, destination_id = "family_memory", row["memory_id"]
        image_id = row["memory_image_id"]
    return Notification(
        id=row["id"],
        type=ntype,
        message=message,
        request_id=row["request_id"],
        story_id=row["story_id"],
        invite_id=row["invite_id"],
        memory_id=row["memory_id"],
        related_image_media_id=image_id,
        destination_type=destination_type,
        destination_id=destination_id,
        read_at=row["read_at"],
        created_at=row["created_at"],
    )


def _recipient_clause() -> str:
    return """
      (n.recipient_user_id = $1 or n.recipient_id in (
        select person_id from member where user_id = $1 and person_id is not null
      ))
    """


def _valid_reference_clause() -> str:
    return """
      (
        (n.type = 'request_received' and exists (
          select 1 from story_request visible_request
          join heirloom request_object on request_object.id = visible_request.heirloom_id
          join member request_member on request_member.family_id = request_object.family_id
          where visible_request.id = n.request_id and request_member.user_id = $1
            and visible_request.storyteller_id = n.recipient_id
        ))
        or (n.type = 'request_declined' and exists (
          select 1 from story_request visible_request
          join heirloom request_object on request_object.id = visible_request.heirloom_id
          join member request_member on request_member.family_id = request_object.family_id
          where visible_request.id = n.request_id and request_member.user_id = $1
            and visible_request.listener_id = n.recipient_id
        ))
        or (n.type = 'story_ready' and exists (
          select 1 from story visible_story
          join heirloom story_object on story_object.id = visible_story.heirloom_id
          join member story_member on story_member.family_id = story_object.family_id
          where visible_story.id = n.story_id and visible_story.status = 'published'
            and story_member.user_id = $1
        ))
        or (n.type = 'memory_added' and exists (
          select 1 from family_memory visible_memory
          join member memory_member on memory_member.family_id = visible_memory.family_id
          where visible_memory.id = n.memory_id and visible_memory.status = 'published'
            and memory_member.user_id = $1
        ))
        or (n.type = 'invite_received' and exists (
          select 1 from family_invite visible_invite
          join auth.users recipient_user on recipient_user.id = $1
          where visible_invite.id = n.invite_id
            and visible_invite.email = lower(recipient_user.email)
            and recipient_user.email_confirmed_at is not null
        ))
        or (n.type in ('invite_accepted', 'invite_declined') and exists (
          select 1 from family_invite visible_invite
          where visible_invite.id = n.invite_id and visible_invite.inviter_user_id = $1
        ))
      )
    """


@router.get("")
async def list_notifications(
    user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
) -> list[Notification]:
    if not 1 <= limit <= MAX_PAGE_SIZE or not 0 <= offset <= MAX_OFFSET:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid pagination")
    async with pool().acquire() as conn:
        await _sync_pending_invites(conn, user.id)
        rows = await conn.fetch(
            _SELECT
            + " where "
            + _recipient_clause()
            + " and "
            + _valid_reference_clause()
            + " and (not $2::boolean or n.read_at is null)"
            + " order by (n.read_at is null) desc, n.created_at desc, n.id desc "
            + "limit $3 offset $4",
            user.id,
            unread_only,
            limit,
            offset,
        )
    return [_notification(row) for row in rows]


@router.get("/unread-count")
async def unread_count(user: CurrentUser) -> UnreadCount:
    async with pool().acquire() as conn:
        await _sync_pending_invites(conn, user.id)
        count = await conn.fetchval(
            "select count(*) from notification n where "
            + _recipient_clause()
            + " and "
            + _valid_reference_clause()
            + " and n.read_at is null",
            user.id,
        )
    return UnreadCount(count=count)


@router.post("/{notification_id}/read")
async def mark_read(notification_id: UUID, user: CurrentUser) -> Notification:
    async with pool().acquire() as conn, conn.transaction():
        changed = await conn.fetchval(
            "update notification n set read_at = coalesce(n.read_at, now()) "
            "where n.id = $2 and "
            + _recipient_clause()
            + " and "
            + _valid_reference_clause()
            + " returning n.id",
            user.id,
            notification_id,
        )
        if changed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
        row = await conn.fetchrow(_SELECT + " where n.id = $1", notification_id)
    return _notification(row)
