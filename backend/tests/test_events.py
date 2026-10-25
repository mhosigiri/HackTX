"""Important Dates: scoped CRUD, bounded recurrence projection, time zones, and RLS."""

import asyncio
from datetime import date, time
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app.auth import User
from app.routers import events, families
from app.routers.events import CreateEvent, UpdateEvent
from app.routers.families import CreateFamily
from tests.test_brief_fixes import visible


async def status_of(call) -> int:
    with pytest.raises(HTTPException) as exc:
        await call
    return exc.value.status_code


async def add_user(conn, email: str) -> User:
    user = User(id=uuid4())
    await conn.execute("insert into auth.users (id, email) values ($1, $2)", user.id, email)
    return user


async def test_event_crud_projects_annual_february_29_and_preserves_local_time(conn, seed):
    related = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, 'Maya') returning id",
        seed.family_id,
    )
    created = await events.create_event(
        seed.family_id,
        CreateEvent(
            title="  Nani's birthday  ",
            category="birthday",
            date=date(2024, 2, 29),
            time=time(9, 30),
            time_zone="America/Chicago",
            description=" Cake at home ",
            related_person_ids=[related],
            repeats_annually=True,
        ),
        User(seed.user_id),
    )
    assert created.title == "Nani's birthday"
    assert created.description == "Cake at home"
    assert created.time == time(9, 30)
    assert created.related_person_ids == [related]

    occurrences = await events.list_events(
        seed.family_id,
        date(2023, 2, 28),
        date(2024, 2, 29),
        User(seed.user_id),
    )
    assert [item.occurrence_date for item in occurrences] == [date(2023, 2, 28), date(2024, 2, 29)]
    assert all(item.occurrence_at.hour == 9 for item in occurrences)
    assert occurrences[0].occurrence_at.utcoffset().total_seconds() == -6 * 3600

    updated = await events.update_event(
        created.id,
        UpdateEvent(title="Nani's birthday tea", time=None),
        User(seed.user_id),
    )
    assert updated.title == "Nani's birthday tea"
    assert updated.time is None and updated.time_zone is None
    assert (await events.get_event(created.id, User(seed.user_id))).id == created.id

    response = await events.delete_event(created.id, User(seed.user_id))
    assert response.status_code == 204
    assert await conn.fetchval("select count(*) from family_event where id = $1", created.id) == 0


async def test_create_is_idempotent_under_concurrent_retries(conn, seed):
    body = CreateEvent(
        title="Family lunch",
        category="family_function",
        date=date(2026, 11, 1),
        idempotency_key="calendar-save-1",
    )
    first, second = await asyncio.gather(
        events.create_event(seed.family_id, body, User(seed.user_id)),
        events.create_event(seed.family_id, body, User(seed.user_id)),
    )
    assert first.id == second.id
    assert (
        await conn.fetchval(
            "select count(*) from family_event where idempotency_key = 'calendar-save-1'"
        )
        == 1
    )


async def test_event_access_is_family_scoped_and_only_creator_mutates(conn, seed):
    relative = await add_user(conn, "relative@example.com")
    relative_person = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, 'Relative') returning id",
        seed.family_id,
    )
    await conn.execute(
        "insert into member (user_id, family_id, person_id) values ($1, $2, $3)",
        relative.id,
        seed.family_id,
        relative_person,
    )
    outsider = await add_user(conn, "outsider@example.com")
    other = await families.create_family(CreateFamily(name="Other", your_name="Out"), outsider)

    created = await events.create_event(
        seed.family_id,
        CreateEvent(
            title="Anniversary",
            category="anniversary",
            date=date(2026, 7, 1),
            related_person_ids=[relative_person],
        ),
        User(seed.user_id),
    )
    assert (await events.get_event(created.id, relative)).id == created.id
    assert await status_of(events.get_event(created.id, outsider)) == 403
    assert (
        await status_of(
            events.list_events(seed.family_id, date(2026, 1, 1), date(2026, 12, 31), outsider)
        )
        == 403
    )
    assert (
        await status_of(events.update_event(created.id, UpdateEvent(title="Changed"), relative))
        == 403
    )
    assert await status_of(events.delete_event(created.id, relative)) == 403
    assert await events.list_events(other.id, date(2026, 1, 1), date(2026, 12, 31), outsider) == []

    sql = "select count(*) from family_event"
    assert await visible(conn, seed.user_id, sql) == 1
    assert await visible(conn, relative.id, sql) == 1
    assert await visible(conn, outsider.id, sql) == 0
    link_sql = "select count(*) from family_event_person"
    assert await visible(conn, seed.user_id, link_sql) == 1
    assert await visible(conn, relative.id, link_sql) == 1
    assert await visible(conn, outsider.id, link_sql) == 0


async def test_range_ordering_handles_day_month_year_and_utc_boundaries(conn, seed):
    await events.create_event(
        seed.family_id,
        CreateEvent(
            title="New Year's Eve",
            category="family_function",
            date=date(2026, 12, 31),
        ),
        User(seed.user_id),
    )
    new_year = await events.create_event(
        seed.family_id,
        CreateEvent(
            title="New Year breakfast",
            category="family_function",
            date=date(2027, 1, 1),
            time=time(0, 30),
            time_zone="Asia/Kolkata",
        ),
        User(seed.user_id),
    )

    whole = await events.list_events(
        seed.family_id,
        date(2026, 12, 31),
        date(2027, 1, 1),
        User(seed.user_id),
    )
    assert [item.title for item in whole] == ["New Year's Eve", "New Year breakfast"]
    assert whole[1].occurrence_at.isoformat() == "2027-01-01T00:30:00+05:30"
    stored = await conn.fetchval("select event_at from family_event where id = $1", new_year.id)
    assert stored.date() == date(2026, 12, 31), "the instant is previous-day UTC"

    second_page = await events.list_events(
        seed.family_id,
        date(2026, 12, 31),
        date(2027, 1, 1),
        User(seed.user_id),
        limit=1,
        offset=1,
    )
    assert [item.id for item in second_page] == [new_year.id]


async def test_event_validation_bounds_and_database_integrity(conn, seed):
    with pytest.raises(ValueError):
        CreateEvent(
            title="Festival",
            category="cultural_function",
            date=date(2026, 10, 20),
            repeats_annually=True,
        )
    with pytest.raises(ValueError):
        CreateEvent(
            title="Dinner",
            category="family_function",
            date=date(2026, 10, 20),
            time=time(18),
        )
    with pytest.raises(ValueError):
        CreateEvent(
            title="Dinner",
            category="family_function",
            date=date(2026, 10, 20),
            time=time(18),
            time_zone="Mars/Olympus_Mons",
        )
    with pytest.raises(ValueError):
        CreateEvent(
            title="Nonexistent wall time",
            category="other",
            date=date(2026, 3, 8),
            time=time(2, 30),
            time_zone="America/Chicago",
        )

    assert (
        await status_of(
            events.list_events(
                seed.family_id, date(2025, 1, 1), date(2026, 12, 31), User(seed.user_id)
            )
        )
        == 422
    )
    assert (
        await status_of(
            events.list_events(
                seed.family_id, date(2026, 2, 1), date(2026, 1, 1), User(seed.user_id)
            )
        )
        == 422
    )

    outsider = await add_user(conn, "cross-family@example.com")
    other = await families.create_family(
        CreateFamily(name="Elsewhere", your_name="Other"), outsider
    )
    other_person = (await families.get_tree(other.id, outsider)).me
    before = await conn.fetchval("select count(*) from family_event")
    assert (
        await status_of(
            events.create_event(
                seed.family_id,
                CreateEvent(
                    title="Bad link",
                    category="other",
                    date=date(2026, 1, 1),
                    related_person_ids=[other_person],
                ),
                User(seed.user_id),
            )
        )
        == 422
    )
    assert await conn.fetchval("select count(*) from family_event") == before

    event_id = uuid4()
    await conn.execute(
        "insert into family_event (id, family_id, created_by, title, category, event_date) "
        "values ($1, $2, $3, 'Test', 'other', '2026-01-01')",
        event_id,
        seed.family_id,
        seed.user_id,
    )
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await conn.execute(
            "insert into family_event_person (event_id, family_id, person_id) values ($1, $2, $3)",
            event_id,
            seed.family_id,
            other_person,
        )
