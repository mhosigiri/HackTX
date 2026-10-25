"""Family availability: private schedules, narrow status, recurrence, and overrides."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import User
from app.routers import availability, families
from app.routers.availability import (
    CreateBusyPeriod,
    SetAvailabilityOverride,
    UpdateAvailabilitySettings,
    UpdateBusyPeriod,
)
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


async def add_family_member(conn, family_id, user: User, name: str):
    person_id = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, $2) returning id",
        family_id,
        name,
    )
    await conn.execute(
        "insert into member (user_id, family_id, person_id) values ($1, $2, $3)",
        user.id,
        family_id,
        person_id,
    )
    return person_id


def fixed_now(monkeypatch, value: datetime) -> None:
    monkeypatch.setattr(availability, "now_utc", lambda: value)


async def test_owner_only_busy_period_crud_and_idempotency(conn, seed):
    owner = User(seed.user_id)
    other = await add_user(conn, "other@example.com")
    body = CreateBusyPeriod(
        private_label="  Work  ",
        start_date=date(2026, 10, 26),
        start_time=time(9),
        end_time=time(17),
        time_zone="America/Chicago",
        repeat_weekdays=[0, 1, 2, 3, 4],
        repeat_until=date(2027, 10, 26),
        idempotency_key="work-week",
    )
    created = await availability.create_busy_period(body, owner)
    retried = await availability.create_busy_period(body, owner)
    assert created.id == retried.id
    assert created.private_label == "Work"
    assert (await availability.get_busy_period(created.id, owner)).id == created.id
    assert [entry.id for entry in await availability.list_busy_periods(owner)] == [created.id]

    assert await status_of(availability.get_busy_period(created.id, other)) == 404
    assert (
        await status_of(
            availability.update_busy_period(
                created.id, UpdateBusyPeriod(private_label="Mine"), other
            )
        )
        == 404
    )
    assert await status_of(availability.delete_busy_period(created.id, other)) == 404

    updated = await availability.update_busy_period(
        created.id,
        UpdateBusyPeriod(private_label="Office", repeat_weekdays=[], repeat_until=None),
        owner,
    )
    assert updated.private_label == "Office"
    assert updated.repeat_weekdays == [] and updated.repeat_until is None
    assert (await availability.delete_busy_period(created.id, owner)).status_code == 204
    assert await availability.list_busy_periods(owner) == []


async def test_status_precedence_disabled_override_expiry_and_schedule(conn, seed, monkeypatch):
    now = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)  # Monday, 10:00 Chicago
    fixed_now(monkeypatch, now)
    owner = User(seed.user_id)
    relative = await add_user(conn, "relative@example.com")
    relative_person = await add_family_member(conn, seed.family_id, relative, "Relative")
    await availability.create_busy_period(
        CreateBusyPeriod(
            private_label="Private work label",
            start_date=date(2026, 10, 26),
            start_time=time(9),
            end_time=time(17),
            time_zone="America/Chicago",
        ),
        owner,
    )

    # Sharing is opt-in even when a busy row exists.
    initial = await availability.list_family_availability(seed.family_id, relative)
    mine = next(item for item in initial if item.person_id == seed.narrator_id)
    assert mine.status == "not_shared"
    assert set(mine.model_dump()) == {"person_id", "display_name", "status", "last_updated_at"}

    # Sharing without confirming the schedule is still not shared.
    await availability.update_availability_settings(
        UpdateAvailabilitySettings(sharing_enabled=True), owner
    )
    mine = next(
        item
        for item in await availability.list_family_availability(seed.family_id, relative)
        if item.person_id == seed.narrator_id
    )
    assert mine.status == "not_shared"

    # An active override takes precedence once sharing is enabled, even before configuration.
    await availability.set_availability_override(
        SetAvailabilityOverride(status="free", expires_at=now + timedelta(minutes=30)), owner
    )
    mine = next(
        item
        for item in await availability.list_family_availability(seed.family_id, relative)
        if item.person_id == seed.narrator_id
    )
    assert mine.status == "free_now"

    # After expiry, schedule derivation resumes. The active work interval is busy.
    await availability.update_availability_settings(
        UpdateAvailabilitySettings(schedule_configured=True), owner
    )
    fixed_now(monkeypatch, now + timedelta(minutes=31))
    mine = next(
        item
        for item in await availability.list_family_availability(seed.family_id, relative)
        if item.person_id == seed.narrator_id
    )
    assert mine.status == "busy_now"

    # Disabling sharing wins even over a still-active manual override.
    fixed_now(monkeypatch, now)
    await availability.set_availability_override(
        SetAvailabilityOverride(status="busy", expires_at=now + timedelta(hours=1)), owner
    )
    await availability.update_availability_settings(
        UpdateAvailabilitySettings(sharing_enabled=False), owner
    )
    mine = next(
        item
        for item in await availability.list_family_availability(seed.family_id, relative)
        if item.person_id == seed.narrator_id
    )
    assert mine.status == "not_shared"
    assert (
        next(item for item in initial if item.person_id == relative_person).status == "not_shared"
    )


async def test_recurrence_cross_midnight_boundaries_and_timezones(conn, seed, monkeypatch):
    owner = User(seed.user_id)
    await availability.update_availability_settings(
        UpdateAvailabilitySettings(sharing_enabled=True, schedule_configured=True), owner
    )
    await availability.create_busy_period(
        CreateBusyPeriod(
            start_date=date(2026, 10, 26),  # Monday
            start_time=time(23),
            end_time=time(1),
            time_zone="America/Chicago",
            repeat_weekdays=[0],
            repeat_until=date(2027, 10, 26),
        ),
        owner,
    )

    async def mine_at(value: datetime):
        fixed_now(monkeypatch, value)
        return next(
            item
            for item in await availability.list_family_availability(seed.family_id, owner)
            if item.person_id == seed.narrator_id
        )

    assert (await mine_at(datetime(2026, 10, 27, 5, 30, tzinfo=UTC))).status == "busy_now"
    assert (await mine_at(datetime(2026, 10, 27, 6, 0, tzinfo=UTC))).status == "free_now"

    # A local New Year interval in India is active while UTC is still December 31.
    await availability.create_busy_period(
        CreateBusyPeriod(
            start_date=date(2027, 1, 1),
            start_time=time(0),
            end_time=time(1),
            time_zone="Asia/Kolkata",
        ),
        owner,
    )
    assert (await mine_at(datetime(2026, 12, 31, 18, 45, tzinfo=UTC))).status == "busy_now"


async def test_cross_family_access_and_direct_database_privacy(conn, seed, monkeypatch):
    now = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
    fixed_now(monkeypatch, now)
    owner = User(seed.user_id)
    relative = await add_user(conn, "relative@example.com")
    await add_family_member(conn, seed.family_id, relative, "Relative")
    outsider = await add_user(conn, "outsider@example.com")
    other_family = await families.create_family(
        CreateFamily(name="Other", your_name="Outsider"), outsider
    )

    await availability.update_availability_settings(
        UpdateAvailabilitySettings(
            sharing_enabled=True, schedule_configured=True, time_zone="America/Chicago"
        ),
        owner,
    )
    await availability.create_busy_period(
        CreateBusyPeriod(
            private_label="Secret appointment",
            start_date=date(2026, 10, 26),
            start_time=time(9),
            end_time=time(17),
            time_zone="America/Chicago",
        ),
        owner,
    )

    assert await status_of(availability.list_family_availability(seed.family_id, outsider)) == 403
    assert [
        item.status
        for item in await availability.list_family_availability(other_family.id, outsider)
    ] == ["not_shared"]

    setting_sql = "select count(*) from availability_setting"
    schedule_sql = "select count(*) from private_schedule_entry"
    assert await visible(conn, owner.id, setting_sql) == 1
    assert await visible(conn, owner.id, schedule_sql) == 1
    assert await visible(conn, relative.id, setting_sql) == 0
    assert await visible(conn, relative.id, schedule_sql) == 0
    assert await visible(conn, outsider.id, setting_sql) == 0
    assert await visible(conn, outsider.id, schedule_sql) == 0
    assert not await conn.fetchval(
        "select has_table_privilege('authenticated', 'availability_setting', 'insert')"
    )
    assert not await conn.fetchval(
        "select has_table_privilege('authenticated', 'private_schedule_entry', 'update')"
    )


def test_schedule_and_override_validation_is_bounded():
    with pytest.raises(ValueError):
        CreateBusyPeriod(
            start_date=date(2026, 1, 1),
            start_time=time(9),
            end_time=time(17),
            time_zone="America/Chicago",
            repeat_weekdays=[0],
        )
    with pytest.raises(ValueError):
        CreateBusyPeriod(
            start_date=date(2026, 1, 1),
            start_time=time(9),
            end_time=time(17),
            time_zone="America/Chicago",
            repeat_weekdays=[0],
            repeat_until=date(2027, 1, 3),
        )
    with pytest.raises(ValueError):
        CreateBusyPeriod(
            start_date=date(2026, 3, 8),
            start_time=time(2, 30),
            end_time=time(4),
            time_zone="America/Chicago",
        )
