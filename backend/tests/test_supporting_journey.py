"""End-to-end supporting backend journey and cross-feature revocation behavior."""

from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import (
    availability,
    events,
    families,
    invites,
    memories,
    notifications,
    profiles,
    timeline,
)
from app.routers.availability import CreateBusyPeriod, UpdateAvailabilitySettings
from app.routers.events import CreateEvent
from app.routers.families import CreateFamily
from app.routers.invites import CreateInvite
from app.routers.profiles import UpdateProfile
from tests.test_invites import add_user
from tests.test_memories import published_memory, visible


async def test_complete_supporting_journey_and_access_revocation(conn, fakes, monkeypatch):
    fixed_now = datetime(2026, 10, 25, 18, 0, tzinfo=UTC)
    monkeypatch.setattr(availability, "now_utc", lambda: fixed_now)

    owner = await add_user(conn, "journey-owner@example.com")
    relative = await add_user(conn, "journey-relative@example.com")
    family = await families.create_family(
        CreateFamily(name="Journey family", your_name="Owner person"), owner
    )
    owner_tree = await families.get_tree(family.id, owner)
    owner_person = owner_tree.me

    avatar_id = uuid4()
    await conn.execute(
        "insert into media (id, family_id, kind, storage_path, mime, created_by) "
        "values ($1, $2, 'photo', $3, 'image/jpeg', $4)",
        avatar_id,
        family.id,
        f"{family.id}/avatars/{avatar_id}.jpg",
        owner.id,
    )
    await conn.execute(
        "update person set avatar_media_id = $2 where id = $1", owner_person, avatar_id
    )
    await profiles.update_profile(UpdateProfile(display_name="Private account name"), owner)

    invitation = await invites.create_invite(
        family.id,
        CreateInvite(
            anchor_person_id=owner_person,
            kind="sibling",
            email="journey-relative@example.com",
        ),
        owner,
    )
    first_inbox = await notifications.list_notifications(relative)
    second_inbox = await notifications.list_notifications(relative)
    assert len(first_inbox) == len(second_inbox) == 1
    assert first_inbox[0].type == "invite_received"
    assert first_inbox[0].related_image_media_id == avatar_id

    accepted = await invites.accept_invite(invitation.id, relative)
    assert accepted.person_id is not None
    tree = await families.get_tree(family.id, relative)
    assert {person.display_name for person in tree.people} == {"Owner person", "journey-relative"}
    assert await visible(conn, relative.id, "select count(*) from profile") == 0

    event = await events.create_event(
        family.id,
        CreateEvent(
            title="Family reunion",
            category="family_function",
            date=date(2026, 10, 25),
            related_person_ids=[accepted.person_id],
        ),
        owner,
    )

    await availability.update_availability_settings(
        UpdateAvailabilitySettings(
            sharing_enabled=True,
            schedule_configured=True,
            time_zone="America/Chicago",
        ),
        relative,
    )
    private_period = await availability.create_busy_period(
        CreateBusyPeriod(
            private_label="Private appointment",
            start_date=date(2026, 10, 25),
            start_time=time(12),
            end_time=time(14),
            time_zone="America/Chicago",
            idempotency_key="journey-busy",
        ),
        relative,
    )
    statuses = await availability.list_family_availability(family.id, owner)
    relative_status = next(item for item in statuses if item.person_id == accepted.person_id)
    assert relative_status.status == "busy_now"
    assert "Private appointment" not in relative_status.model_dump_json()
    assert await visible(conn, owner.id, "select count(*) from private_schedule_entry") == 0

    memory, *_ = await published_memory(
        conn,
        fakes,
        SimpleNamespace(
            family_id=family.id,
            user_id=owner.id,
            narrator_id=owner_person,
        ),
        title="Journey memory",
    )
    await memories.update_family_memory(
        memory.id,
        memories.UpdateFamilyMemory(event_date=date(2026, 10, 25)),
        owner,
    )
    page = await timeline.list_timeline(
        family.id,
        date(2026, 10, 25),
        date(2026, 10, 25),
        relative,
        include_unknown=False,
    )
    assert {(item.source_type, item.source_id) for item in page.items} == {
        ("important_date", event.id),
        ("memory", memory.id),
    }

    inbox = await notifications.list_notifications(relative)
    memory_note = next(item for item in inbox if item.type == "memory_added")
    assert (await notifications.unread_count(relative)).count == 2
    await notifications.mark_read(memory_note.id, relative)
    assert (await notifications.unread_count(relative)).count == 1

    # Retrying an already-published action repairs a lost notification without duplication.
    await conn.execute("delete from notification where id = $1", memory_note.id)
    await memories.publish_family_memory(memory.id, owner)
    repaired = [
        item
        for item in await notifications.list_notifications(relative)
        if item.type == "memory_added"
    ]
    assert len(repaired) == 1
    await memories.publish_family_memory(memory.id, owner)
    assert (
        await conn.fetchval(
            "select count(*) from notification where memory_id = $1 and type = 'memory_added'",
            memory.id,
        )
        == 1
    )

    # A stale notification is hidden consistently while its source is not published.
    await conn.execute("update family_memory set status = 'draft' where id = $1", memory.id)
    assert all(
        item.memory_id != memory.id for item in await notifications.list_notifications(relative)
    )
    assert (await notifications.unread_count(relative)).count == 1
    hidden_page = await timeline.list_timeline(
        family.id,
        date(2026, 10, 25),
        date(2026, 10, 25),
        relative,
        include_unknown=False,
    )
    assert all(item.source_id != memory.id for item in hidden_page.items)
    await conn.execute("update family_memory set status = 'published' where id = $1", memory.id)

    saved_profile = await profiles.update_profile(
        UpdateProfile(age=72, ui_mode="regular", preferred_language="hi"), relative
    )
    assert (
        saved_profile.ui_mode,
        saved_profile.ui_mode_is_manual,
        saved_profile.preferred_language,
    ) == ("regular", True, "hi")

    other = await families.create_family(
        CreateFamily(name="Other journey family", your_name="Relative elsewhere"), relative
    )
    await events.create_event(
        other.id,
        CreateEvent(title="Other private event", category="other", date=date(2026, 10, 25)),
        relative,
    )
    with pytest.raises(HTTPException) as cross_family:
        await timeline.list_timeline(
            other.id,
            date(2026, 10, 25),
            date(2026, 10, 25),
            owner,
        )
    assert cross_family.value.status_code == 403

    await memories.delete_family_memory(memory.id, owner)
    assert (
        await conn.fetchval("select count(*) from notification where memory_id = $1", memory.id)
        == 0
    )

    await conn.execute(
        "delete from member where user_id = $1 and family_id = $2", relative.id, family.id
    )
    with pytest.raises(HTTPException) as removed_timeline:
        await timeline.list_timeline(
            family.id,
            date(2026, 10, 25),
            date(2026, 10, 25),
            relative,
        )
    assert removed_timeline.value.status_code == 403
    with pytest.raises(HTTPException) as removed_availability:
        await availability.list_family_availability(family.id, relative)
    assert removed_availability.value.status_code == 403
    assert (
        await visible(
            conn,
            relative.id,
            "select count(*) from family_event where id = $1",
            event.id,
        )
        == 0
    )
    assert [item.type for item in await notifications.list_notifications(relative)] == [
        "invite_received"
    ]
    assert [entry.id for entry in await availability.list_busy_periods(relative)] == [
        private_period.id
    ]
