"""Family timeline projection: source visibility, dates, recurrence, and pagination."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.auth import User
from app.routers import events, families, timeline
from app.routers.events import CreateEvent
from app.routers.families import CreateFamily


async def add_memory(
    conn,
    seed,
    *,
    title: str,
    event_date: date | None,
    status: str = "published",
    upload_status: str = "ready",
) -> UUID:
    memory_id, photo_id, audio_id = uuid4(), uuid4(), uuid4()
    await conn.execute(
        """
        insert into family_memory
          (id, family_id, contributor_id, created_by, title, description, event_date)
        values ($1, $2, $3, $4, $5, 'A short memory', $6)
        """,
        memory_id,
        seed.family_id,
        seed.narrator_id,
        seed.user_id,
        title,
        event_date,
    )
    await conn.execute(
        """
        insert into media
          (id, family_id, memory_id, kind, storage_path, mime, upload_status,
           byte_size, created_by)
        values ($1, $2, $3, 'photo', $4, 'image/jpeg', $5, 10, $6),
               ($7, $2, $3, 'audio', $8, 'audio/webm', $5, 10, $6)
        """,
        photo_id,
        seed.family_id,
        memory_id,
        f"{seed.family_id}/memories/{memory_id}/{photo_id}.jpg",
        upload_status,
        seed.user_id,
        audio_id,
        f"{seed.family_id}/memories/{memory_id}/{audio_id}.webm",
    )
    await conn.execute(
        "insert into family_memory_photo (memory_id, media_id, position) values ($1, $2, 0)",
        memory_id,
        photo_id,
    )
    published_at = datetime(2026, 10, 25, 12, tzinfo=UTC) if status == "published" else None
    await conn.execute(
        """
        update family_memory
        set status = $2, cover_media_id = $3, recording_media_id = $4, published_at = $5
        where id = $1
        """,
        memory_id,
        status,
        photo_id,
        audio_id,
        published_at,
    )
    return memory_id


async def add_story(
    conn,
    seed,
    *,
    title: str,
    year: int | None,
    status: str = "published",
    request_status: str | None = None,
) -> tuple[UUID, UUID | None]:
    heirloom_id, story_id = uuid4(), uuid4()
    await conn.execute(
        "insert into heirloom (id, family_id, title, created_by) values ($1, $2, $3, $4)",
        heirloom_id,
        seed.family_id,
        title,
        seed.user_id,
    )
    request_id = None
    if request_status is not None:
        storyteller_id = await conn.fetchval(
            "insert into person (family_id, display_name) values ($1, $2) returning id",
            seed.family_id,
            f"{title} teller",
        )
        request_id = await conn.fetchval(
            """
            insert into story_request
              (heirloom_id, listener_id, storyteller_id, status)
            values ($1, $2, $3, $4) returning id
            """,
            heirloom_id,
            seed.narrator_id,
            storyteller_id,
            request_status,
        )
    fact_id = None
    blocks = []
    if year is not None:
        fact_id = await conn.fetchval(
            """
            insert into fact (heirloom_id, kind, text, source, year)
            values ($1, 'memory', $2, '{}'::jsonb, $3) returning id
            """,
            heirloom_id,
            f"{title} happened",
            year,
        )
        blocks = [
            {
                "type": "timeline",
                "events": [{"year": year, "label": f"{title} milestone", "fact_id": str(fact_id)}],
            }
        ]
    await conn.execute(
        """
        insert into story
          (id, heirloom_id, version, title, dek, blocks, request_id, status)
        values ($1, $2, 1, $3, 'Story summary', $4::jsonb, $5, $6)
        """,
        story_id,
        heirloom_id,
        title,
        blocks,
        request_id,
        status,
    )
    return story_id, fact_id


async def test_mixed_sources_order_pagination_and_private_exclusions(conn, seed):
    completed_story, fact_id = await add_story(
        conn, seed, title="Wedding story", year=1960, request_status="completed"
    )
    unknown_story, _ = await add_story(conn, seed, title="Undated story", year=None)
    await add_story(conn, seed, title="Draft story", year=1961, status="draft")
    await add_story(conn, seed, title="Pending story", year=1962, request_status="pending")
    memory_id = await add_memory(conn, seed, title="Summer reunion", event_date=date(1965, 7, 4))
    await add_memory(conn, seed, title="Undated memory", event_date=None)
    await add_memory(
        conn,
        seed,
        title="Pending upload",
        event_date=date(1964, 1, 1),
        upload_status="uploading",
    )
    await add_memory(conn, seed, title="Private draft", event_date=date(1963, 1, 1), status="draft")
    event = await events.create_event(
        seed.family_id,
        CreateEvent(
            title="Family picnic",
            category="family_function",
            date=date(1968, 6, 1),
        ),
        User(seed.user_id),
    )

    first = await timeline.list_timeline(
        seed.family_id,
        date(1960, 1, 1),
        date(1969, 12, 31),
        User(seed.user_id),
        limit=2,
    )
    second = await timeline.list_timeline(
        seed.family_id,
        date(1960, 1, 1),
        date(1969, 12, 31),
        User(seed.user_id),
        limit=2,
        offset=2,
    )
    items = [*first.items, *second.items]

    assert first.next_offset == 2 and second.next_offset is None
    assert [item.source_type for item in items] == [
        "story",
        "memory",
        "important_date",
        "story",
    ]
    assert [item.source_id for item in items] == [
        completed_story,
        memory_id,
        event.id,
        unknown_story,
    ]
    assert len({item.item_key for item in items}) == 4

    story_item, memory_item, _, unknown_item = items
    assert story_item.relevant_date is None
    assert story_item.relevant_year == 1960
    assert story_item.date_precision == "year"
    assert story_item.fact_id == fact_id
    assert memory_item.event_date == date(1965, 7, 4)
    assert memory_item.relevant_date == memory_item.event_date
    assert memory_item.published_at.date() == date(2026, 10, 25)
    assert unknown_item.relevant_date is None
    assert unknown_item.relevant_year is None
    assert unknown_item.date_precision == "unknown"


async def test_boundaries_recurrence_and_unknown_option(conn, seed, monkeypatch):
    annual = await events.create_event(
        seed.family_id,
        CreateEvent(
            title="Leap birthday",
            category="birthday",
            date=date(2024, 2, 29),
            repeats_annually=True,
        ),
        User(seed.user_id),
    )
    story_id, _ = await add_story(conn, seed, title="Year-only", year=2023)
    await add_story(conn, seed, title="No historical date", year=None)

    page = await timeline.list_timeline(
        seed.family_id,
        date(2023, 2, 28),
        date(2024, 2, 29),
        User(seed.user_id),
        include_unknown=False,
    )
    annual_items = [item for item in page.items if item.source_id == annual.id]
    assert [item.relevant_date for item in annual_items] == [
        date(2023, 2, 28),
        date(2024, 2, 29),
    ]
    assert [item.original_date for item in annual_items] == [date(2024, 2, 29)] * 2
    assert any(item.source_id == story_id for item in page.items)
    assert all(item.date_precision != "unknown" for item in page.items)

    single_day = await timeline.list_timeline(
        seed.family_id,
        date(2023, 12, 31),
        date(2023, 12, 31),
        User(seed.user_id),
        include_unknown=False,
    )
    assert [item.source_id for item in single_day.items] == [story_id]

    bounded_history = await timeline.list_timeline(
        seed.family_id,
        date(2010, 2, 28),
        date(2020, 2, 29),
        User(seed.user_id),
        include_unknown=False,
    )
    assert len([item for item in bounded_history.items if item.source_id == annual.id]) == 11

    def database_must_not_be_touched():
        raise AssertionError("invalid timeline bounds reached the database")

    monkeypatch.setattr(timeline, "pool", database_must_not_be_touched)

    with pytest.raises(HTTPException) as too_much_expansion:
        await timeline.list_timeline(
            seed.family_id,
            date(2010, 1, 1),
            date(2020, 1, 10),
            User(seed.user_id),
        )
    assert too_much_expansion.value.status_code == 422

    with pytest.raises(HTTPException) as backwards:
        await timeline.list_timeline(
            seed.family_id,
            date(2024, 1, 2),
            date(2024, 1, 1),
            User(seed.user_id),
        )
    assert backwards.value.status_code == 422
    with pytest.raises(HTTPException) as unbounded:
        await timeline.list_timeline(
            seed.family_id,
            date(1800, 1, 1),
            date(2020, 1, 1),
            User(seed.user_id),
        )
    assert unbounded.value.status_code == 422


async def test_cross_family_isolation_applies_before_pagination(conn, seed):
    outsider_id = uuid4()
    await conn.execute(
        "insert into auth.users (id, email) values ($1, 'timeline-outsider@example.com')",
        outsider_id,
    )
    other = await families.create_family(
        CreateFamily(name="Other family", your_name="Outsider"), User(outsider_id)
    )
    await events.create_event(
        other.id,
        CreateEvent(title="Other event", category="other", date=date(1990, 1, 1)),
        User(outsider_id),
    )
    await events.create_event(
        seed.family_id,
        CreateEvent(title="Our event", category="other", date=date(1990, 1, 1)),
        User(seed.user_id),
    )

    with pytest.raises(HTTPException) as denied:
        await timeline.list_timeline(
            seed.family_id,
            date(1985, 1, 1),
            date(1995, 1, 1),
            User(outsider_id),
            limit=1,
        )
    assert denied.value.status_code == 403

    own = await timeline.list_timeline(
        seed.family_id,
        date(1985, 1, 1),
        date(1995, 1, 1),
        User(seed.user_id),
        limit=1,
    )
    assert [item.title for item in own.items] == ["Our event"]
