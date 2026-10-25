"""Notifications and account preference persistence, authorization, and retries."""

import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pydantic
import pytest
from fastapi import HTTPException

from app.auth import User
from app.routers import invites, memories, notifications, profiles, requests
from app.routers.invites import CreateInvite
from app.routers.memories import CreateFamilyMemory
from app.routers.profiles import UpdateProfile
from app.routers.requests import CreateRequest
from tests.test_brief_fixes import visible
from tests.test_invites import add_user, new_family
from tests.test_memories import add_member, add_other_family, published_memory


async def add_request(conn, seed, storyteller_id):
    return await conn.fetchval(
        "insert into story_request (heirloom_id, listener_id, storyteller_id) "
        "values ($1, $2, $3) returning id",
        seed.heirloom_id,
        seed.narrator_id,
        storyteller_id,
    )


async def test_recipient_only_pagination_unread_and_read_ownership(conn, fakes, seed):
    relative_user, relative_person = await add_member(conn, seed.family_id, "Relative")
    same_family_user, _ = await add_member(conn, seed.family_id, "Other relative")
    outsider = await add_user(conn, "notification-outsider@example.com")
    await new_family(conn, outsider, "Outsider")

    request_ids = []
    for index in range(3):
        request_id = await add_request(conn, seed, relative_person)
        request_ids.append(request_id)
        assert await notifications.create_notification(
            conn,
            ntype="request_received",
            recipient_id=relative_person,
            request_id=request_id,
        )
        await conn.execute(
            "update notification set created_at = now() + $2 * interval '1 second' "
            "where request_id = $1",
            request_id,
            index,
        )

    private_draft = await memories.create_family_memory(
        seed.family_id, CreateFamilyMemory(title="Private draft"), User(seed.user_id)
    )
    await notifications.create_notification(
        conn,
        ntype="memory_added",
        recipient_id=relative_person,
        memory_id=private_draft.id,
    )
    foreign_family, foreign_user, _ = await add_other_family(conn)
    foreign_memory, *_ = await published_memory(
        conn,
        fakes,
        SimpleNamespace(family_id=foreign_family, user_id=foreign_user),
        title="Another family's published memory",
    )
    await notifications.create_notification(
        conn,
        ntype="memory_added",
        recipient_id=relative_person,
        memory_id=foreign_memory.id,
    )

    first = await notifications.list_notifications(User(relative_user), limit=2)
    second = await notifications.list_notifications(User(relative_user), limit=2, offset=2)
    assert [item.request_id for item in first] == request_ids[::-1][:2]
    assert [item.request_id for item in second] == request_ids[:1]
    assert all(item.destination_type == "story_request" for item in [*first, *second])
    assert (await notifications.unread_count(User(relative_user))).count == 3
    assert await notifications.list_notifications(User(seed.user_id)) == []
    assert await notifications.list_notifications(User(same_family_user)) == []
    assert await notifications.list_notifications(outsider) == []

    read = await notifications.mark_read(first[0].id, User(relative_user))
    assert read.read_at is not None
    assert (await notifications.unread_count(User(relative_user))).count == 2
    assert len(await notifications.list_notifications(User(relative_user), unread_only=True)) == 2
    assert (await notifications.list_notifications(User(relative_user)))[-1].id == read.id
    with pytest.raises(HTTPException) as denied:
        await notifications.mark_read(first[1].id, outsider)
    assert denied.value.status_code == 404

    sql = "select count(*) from notification"
    assert await visible(conn, relative_user, sql) == 3
    assert await visible(conn, same_family_user, sql) == 0
    assert await visible(conn, outsider.id, sql) == 0
    async with conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute(
            "select set_config('request.jwt.claim.sub', $1, true)", str(relative_user)
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute("update notification set read_at = now()")
        await conn.execute("reset role")


async def test_notification_delivery_is_deduplicated_on_retries(conn, seed):
    _, recipient = await add_member(conn, seed.family_id, "Recipient")
    request_id = await add_request(conn, seed, recipient)
    first = await notifications.create_notification(
        conn,
        ntype="request_received",
        recipient_id=recipient,
        request_id=request_id,
    )
    retry = await notifications.create_notification(
        conn,
        ntype="request_received",
        recipient_id=recipient,
        request_id=request_id,
    )
    assert first is True and retry is False
    assert (
        await conn.fetchval("select count(*) from notification where request_id = $1", request_id)
        == 1
    )


async def test_originating_request_retry_repairs_missing_notification(
    conn, fakes, seed, monkeypatch
):
    async def signed_url(bucket, path):
        return f"https://storage.test/{bucket}/{path}"

    monkeypatch.setattr(requests, "signed_download_url", signed_url)
    _, storyteller = await add_member(conn, seed.family_id, "Retry storyteller")
    body = CreateRequest(
        heirloom_id=seed.heirloom_id,
        storyteller_id=storyteller,
        message="Please share this story",
        idempotency_key="repair-request-notification",
    )
    created = await requests.create_request(body, User(seed.user_id))
    await conn.execute("delete from notification where request_id = $1", created.id)

    retried = await requests.create_request(body, User(seed.user_id))
    assert retried.id == created.id
    assert (
        await conn.fetchval(
            "select count(*) from notification where request_id = $1 and type = 'request_received'",
            created.id,
        )
        == 1
    )


async def test_notification_failure_log_is_observable_and_redacted(caplog):
    private_marker = str(uuid4())

    class FailedConnection:
        @asynccontextmanager
        async def transaction(self):
            yield

        async def execute(self, *args):
            raise asyncpg.PostgresError(f"private row {private_marker}")

    with caplog.at_level(logging.ERROR, logger="lorebook.notifications"):
        delivered = await notifications.create_notification(
            FailedConnection(),
            ntype="request_received",
            recipient_id=uuid4(),
            request_id=uuid4(),
        )

    assert delivered is False
    message = caplog.records[-1].getMessage()
    assert "type=request_received" in message
    assert "error_class=PostgresError" in message
    assert private_marker not in message


async def test_invitation_and_published_memory_notifications(conn, fakes, seed):
    recipient = await add_user(conn, "notify-invite@example.com")
    owner = User(seed.user_id)
    await conn.execute(
        "update auth.users set email = 'owner-notify@example.com', email_confirmed_at = now() "
        "where id = $1",
        seed.user_id,
    )
    sent = await invites.create_invite(
        seed.family_id,
        CreateInvite(
            anchor_person_id=seed.narrator_id,
            kind="sibling",
            email="notify-invite@example.com",
        ),
        owner,
    )
    received = await notifications.list_notifications(recipient)
    assert [(item.type, item.destination_id) for item in received] == [("invite_received", sent.id)]

    await invites.accept_invite(sent.id, recipient)
    await invites.accept_invite(sent.id, recipient)
    owner_inbox = await notifications.list_notifications(owner)
    assert [item.type for item in owner_inbox] == ["invite_accepted"]

    relative_user, _ = await add_member(conn, seed.family_id, "Memory reader")
    published, *_ = await published_memory(conn, fakes, seed, title="Lake trip")
    await memories.publish_family_memory(published.id, owner)
    memory_notes = [
        item
        for item in await notifications.list_notifications(User(relative_user))
        if item.type == "memory_added"
    ]
    assert len(memory_notes) == 1
    assert memory_notes[0].destination_id == published.id
    assert (
        await conn.fetchval(
            "select count(*) from notification where type = 'memory_added' and memory_id = $1",
            published.id,
        )
        == 2
    ), "one per other accepted member, with no retry duplicates"


async def test_preferred_language_and_manual_display_mode_persist_privately(conn, seed):
    user = User(seed.user_id)
    age_default = await profiles.update_profile(UpdateProfile(age=72), user)
    assert (age_default.ui_mode, age_default.ui_mode_is_manual) == ("extra_simple", False)

    manual = await profiles.update_profile(
        UpdateProfile(ui_mode="regular", preferred_language="es"), user
    )
    assert (manual.ui_mode, manual.ui_mode_is_manual, manual.preferred_language) == (
        "regular",
        True,
        "es",
    )
    changed_age = await profiles.update_profile(UpdateProfile(age=30), user)
    loaded = await profiles.get_profile(user)
    assert changed_age.ui_mode == loaded.ui_mode == "regular"
    assert loaded.preferred_language == "es"

    with pytest.raises(pydantic.ValidationError):
        UpdateProfile(preferred_language="fr")
    with pytest.raises(pydantic.ValidationError):
        UpdateProfile(ui_mode=None)

    relative_id = uuid4()
    await conn.execute("insert into auth.users (id) values ($1)", relative_id)
    relative_person = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, 'Relative') returning id",
        seed.family_id,
    )
    await conn.execute(
        "insert into member (user_id, family_id, person_id) values ($1, $2, $3)",
        relative_id,
        seed.family_id,
        relative_person,
    )
    sql = f"select count(*) from profile where user_id = '{seed.user_id}'"
    assert await visible(conn, seed.user_id, sql) == 1
    assert await visible(conn, relative_id, sql) == 0
