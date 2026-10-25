"""Private schedules and narrow, request-time family availability."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from datetime import time as Time
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth import CurrentUser, require_member
from app.db import pool

router = APIRouter(prefix="/api", tags=["family-availability"])

AvailabilityStatus = Literal["free_now", "busy_now", "not_shared"]
OverrideStatus = Literal["free", "busy"]
Weekday = Annotated[int, Field(ge=0, le=6)]  # Monday=0, Sunday=6
MAX_RECURRENCE_DAYS = 366
MAX_OVERRIDE_DAYS = 7
MAX_SCHEDULE_ENTRIES = 200


def now_utc() -> datetime:
    return datetime.now(UTC)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("time_zone must be a valid IANA time zone") from exc


def _instant(day: Date, clock: Time, zone_name: str) -> datetime:
    """Resolve local wall time with fold=0; nonexistent recurring times move forward."""
    return datetime.combine(day, clock, _zone(zone_name)).replace(fold=0).astimezone(UTC)


def _validate_initial_wall_time(day: Date, clock: Time, zone_name: str) -> None:
    zone = _zone(zone_name)
    local = datetime.combine(day, clock, zone).replace(fold=0)
    round_trip = local.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != datetime.combine(day, clock):
        raise ValueError("schedule time does not exist in that time zone on this date")


class AvailabilitySettings(BaseModel):
    sharing_enabled: bool = False
    schedule_configured: bool = False
    time_zone: str = "UTC"
    override_status: OverrideStatus | None = None
    override_expires_at: datetime | None = None
    updated_at: datetime | None = None


class UpdateAvailabilitySettings(BaseModel):
    sharing_enabled: bool | None = None
    schedule_configured: bool | None = None
    time_zone: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("time_zone")
    @classmethod
    def valid_zone(cls, value: str | None) -> str | None:
        if value is not None:
            _zone(value)
        return value


class SetAvailabilityOverride(BaseModel):
    status: OverrideStatus
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must include a UTC offset")
        return value.astimezone(UTC)


class BusyPeriodValues(BaseModel):
    private_label: str | None = Field(default=None, max_length=80)
    start_date: Date
    start_time: Time
    end_time: Time
    time_zone: str = Field(min_length=1, max_length=64)
    repeat_weekdays: list[Weekday] = Field(default_factory=list, max_length=7)
    repeat_until: Date | None = None

    @field_validator("private_label")
    @classmethod
    def clean_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("private_label cannot be blank")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def local_time_only(cls, value: Time) -> Time:
        if value.tzinfo is not None:
            raise ValueError("times must be local; provide time_zone separately")
        return value

    @field_validator("repeat_weekdays")
    @classmethod
    def unique_weekdays(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("repeat_weekdays must be unique")
        return sorted(value)

    @model_validator(mode="after")
    def valid_period(self):
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time cannot be equal")
        _validate_initial_wall_time(self.start_date, self.start_time, self.time_zone)
        end_date = self.start_date + timedelta(days=self.end_time < self.start_time)
        _validate_initial_wall_time(end_date, self.end_time, self.time_zone)
        if self.repeat_weekdays:
            if self.repeat_until is None:
                raise ValueError("repeat_until is required for repeating schedules")
            days = (self.repeat_until - self.start_date).days
            if not 0 <= days <= MAX_RECURRENCE_DAYS:
                raise ValueError(f"repeating schedules must end within {MAX_RECURRENCE_DAYS} days")
        elif self.repeat_until is not None:
            raise ValueError("repeat_until requires at least one repeat weekday")
        return self


class CreateBusyPeriod(BusyPeriodValues):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class UpdateBusyPeriod(BaseModel):
    private_label: str | None = Field(default=None, max_length=80)
    start_date: Date | None = None
    start_time: Time | None = None
    end_time: Time | None = None
    time_zone: str | None = Field(default=None, min_length=1, max_length=64)
    repeat_weekdays: list[Weekday] | None = Field(default=None, max_length=7)
    repeat_until: Date | None = None


class BusyPeriod(BusyPeriodValues):
    id: UUID
    created_at: datetime
    updated_at: datetime


class FamilyAvailability(BaseModel):
    person_id: UUID
    display_name: str
    status: AvailabilityStatus
    last_updated_at: datetime


def _settings(row: asyncpg.Record | None, now: datetime) -> AvailabilitySettings:
    if row is None:
        return AvailabilitySettings()
    active = row["override_expires_at"] is not None and row["override_expires_at"] > now
    return AvailabilitySettings(
        sharing_enabled=row["sharing_enabled"],
        schedule_configured=row["schedule_configured"],
        time_zone=row["time_zone"],
        override_status=row["override_status"] if active else None,
        override_expires_at=row["override_expires_at"] if active else None,
        updated_at=row["updated_at"],
    )


def _busy_period(row: asyncpg.Record) -> BusyPeriod:
    return BusyPeriod(
        id=row["id"],
        private_label=row["private_label"],
        start_date=row["start_date"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        time_zone=row["time_zone"],
        repeat_weekdays=list(row["repeat_weekdays"]),
        repeat_until=row["repeat_until"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _starts_on(entry: BusyPeriod, day: Date) -> bool:
    if entry.repeat_weekdays:
        return (
            entry.start_date <= day <= entry.repeat_until and day.weekday() in entry.repeat_weekdays
        )
    return day == entry.start_date


def _is_active(entry: BusyPeriod, now: datetime) -> bool:
    local_day = now.astimezone(_zone(entry.time_zone)).date()
    for day in (local_day, local_day - timedelta(days=1)):
        if not _starts_on(entry, day):
            continue
        start = _instant(day, entry.start_time, entry.time_zone)
        end_day = day + timedelta(days=entry.end_time < entry.start_time)
        end = _instant(end_day, entry.end_time, entry.time_zone)
        if start <= now < end:
            return True
    return False


def _derive_status(
    settings: AvailabilitySettings | None,
    entries: list[BusyPeriod],
    now: datetime,
) -> AvailabilityStatus:
    if settings is None or not settings.sharing_enabled:
        return "not_shared"
    if settings.override_status == "free":
        return "free_now"
    if settings.override_status == "busy":
        return "busy_now"
    if not settings.schedule_configured:
        return "not_shared"
    return "busy_now" if any(_is_active(entry, now) for entry in entries) else "free_now"


async def _settings_row(conn: asyncpg.Connection, user_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("select * from availability_setting where user_id = $1", user_id)


async def _entry(
    conn: asyncpg.Connection, entry_id: UUID, user_id: UUID, *, lock: bool = False
) -> BusyPeriod:
    suffix = " for update" if lock else ""
    row = await conn.fetchrow(
        "select * from private_schedule_entry where id = $1 and user_id = $2" + suffix,
        entry_id,
        user_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "busy period not found")
    return _busy_period(row)


@router.get("/availability/settings")
async def get_availability_settings(user: CurrentUser) -> AvailabilitySettings:
    now = now_utc()
    async with pool().acquire() as conn:
        return _settings(await _settings_row(conn, user.id), now)


@router.patch("/availability/settings")
async def update_availability_settings(
    body: UpdateAvailabilitySettings, user: CurrentUser
) -> AvailabilitySettings:
    if not body.model_fields_set:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide at least one change")
    now = now_utc()
    async with pool().acquire() as conn:
        current = _settings(await _settings_row(conn, user.id), now)
        sharing = (
            body.sharing_enabled if body.sharing_enabled is not None else current.sharing_enabled
        )
        configured = (
            body.schedule_configured
            if body.schedule_configured is not None
            else current.schedule_configured
        )
        zone = body.time_zone if body.time_zone is not None else current.time_zone
        row = await conn.fetchrow(
            """
            insert into availability_setting
              (user_id, sharing_enabled, schedule_configured, time_zone, updated_at)
            values ($1, $2, $3, $4, $5)
            on conflict (user_id) do update set
              sharing_enabled = excluded.sharing_enabled,
              schedule_configured = excluded.schedule_configured,
              time_zone = excluded.time_zone,
              updated_at = excluded.updated_at
            returning *
            """,
            user.id,
            sharing,
            configured,
            zone,
            now,
        )
    return _settings(row, now)


@router.put("/availability/override")
async def set_availability_override(
    body: SetAvailabilityOverride, user: CurrentUser
) -> AvailabilitySettings:
    now = now_utc()
    if body.expires_at <= now:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "override expiry must be future")
    if body.expires_at > now + timedelta(days=MAX_OVERRIDE_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"override cannot last more than {MAX_OVERRIDE_DAYS} days",
        )
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into availability_setting
              (user_id, override_status, override_expires_at, updated_at)
            values ($1, $2, $3, $4)
            on conflict (user_id) do update set
              override_status = excluded.override_status,
              override_expires_at = excluded.override_expires_at,
              updated_at = excluded.updated_at
            returning *
            """,
            user.id,
            body.status,
            body.expires_at,
            now,
        )
    return _settings(row, now)


@router.delete("/availability/override", status_code=status.HTTP_204_NO_CONTENT)
async def clear_availability_override(user: CurrentUser) -> Response:
    async with pool().acquire() as conn:
        await conn.execute(
            "update availability_setting set override_status = null, "
            "override_expires_at = null, updated_at = now() where user_id = $1",
            user.id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/availability/schedule")
async def list_busy_periods(
    user: CurrentUser, limit: int = 100, offset: int = 0
) -> list[BusyPeriod]:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid pagination")
    async with pool().acquire() as conn:
        rows = await conn.fetch(
            "select * from private_schedule_entry where user_id = $1 "
            "order by start_date, start_time, id limit $2 offset $3",
            user.id,
            limit,
            offset,
        )
    return [_busy_period(row) for row in rows]


@router.post("/availability/schedule", status_code=status.HTTP_201_CREATED)
async def create_busy_period(body: CreateBusyPeriod, user: CurrentUser) -> BusyPeriod:
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "select pg_advisory_xact_lock(hashtextextended($1::uuid::text, 0))", user.id
        )
        if body.idempotency_key:
            existing = await conn.fetchval(
                "select id from private_schedule_entry where user_id = $1 and idempotency_key = $2",
                user.id,
                body.idempotency_key,
            )
            if existing:
                return await _entry(conn, existing, user.id)
        count = await conn.fetchval(
            "select count(*) from private_schedule_entry where user_id = $1", user.id
        )
        if count >= MAX_SCHEDULE_ENTRIES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"a schedule cannot contain more than {MAX_SCHEDULE_ENTRIES} busy periods",
            )
        entry_id = await conn.fetchval(
            """
            insert into private_schedule_entry
              (user_id, private_label, start_date, start_time, end_time, time_zone,
               repeat_weekdays, repeat_until, idempotency_key)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            on conflict (user_id, idempotency_key) where idempotency_key is not null
              do nothing
            returning id
            """,
            user.id,
            body.private_label,
            body.start_date,
            body.start_time,
            body.end_time,
            body.time_zone,
            body.repeat_weekdays,
            body.repeat_until,
            body.idempotency_key,
        )
        if entry_id is None:
            entry_id = await conn.fetchval(
                "select id from private_schedule_entry where user_id = $1 and idempotency_key = $2",
                user.id,
                body.idempotency_key,
            )
        return await _entry(conn, entry_id, user.id)


@router.get("/availability/schedule/{entry_id}")
async def get_busy_period(entry_id: UUID, user: CurrentUser) -> BusyPeriod:
    async with pool().acquire() as conn:
        return await _entry(conn, entry_id, user.id)


@router.patch("/availability/schedule/{entry_id}")
async def update_busy_period(
    entry_id: UUID, body: UpdateBusyPeriod, user: CurrentUser
) -> BusyPeriod:
    if not body.model_fields_set:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide at least one change")
    async with pool().acquire() as conn, conn.transaction():
        current = await _entry(conn, entry_id, user.id, lock=True)
        values = current.model_dump(
            include={
                "private_label",
                "start_date",
                "start_time",
                "end_time",
                "time_zone",
                "repeat_weekdays",
                "repeat_until",
            }
        )
        for field in body.model_fields_set:
            values[field] = getattr(body, field)
        if "repeat_weekdays" in body.model_fields_set and not body.repeat_weekdays:
            values["repeat_until"] = None
        try:
            changed = CreateBusyPeriod.model_validate(values)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        await conn.execute(
            """
            update private_schedule_entry set private_label = $2, start_date = $3,
              start_time = $4, end_time = $5, time_zone = $6, repeat_weekdays = $7,
              repeat_until = $8, updated_at = now()
            where id = $1 and user_id = $9
            """,
            entry_id,
            changed.private_label,
            changed.start_date,
            changed.start_time,
            changed.end_time,
            changed.time_zone,
            changed.repeat_weekdays,
            changed.repeat_until,
            user.id,
        )
        return await _entry(conn, entry_id, user.id)


@router.delete("/availability/schedule/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_busy_period(entry_id: UUID, user: CurrentUser) -> Response:
    async with pool().acquire() as conn, conn.transaction():
        await _entry(conn, entry_id, user.id, lock=True)
        await conn.execute(
            "delete from private_schedule_entry where id = $1 and user_id = $2",
            entry_id,
            user.id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/families/{family_id}/availability")
async def list_family_availability(
    family_id: UUID, user: CurrentUser, limit: int = 100, offset: int = 0
) -> list[FamilyAvailability]:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid pagination")
    now = now_utc()
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        members = await conn.fetch(
            """
            select m.user_id, m.person_id, p.display_name
            from member m join person p on p.id = m.person_id
            where m.family_id = $1 and m.person_id is not null
            order by lower(p.display_name), p.id
            limit $2 offset $3
            """,
            family_id,
            limit,
            offset,
        )
        user_ids = [row["user_id"] for row in members]
        if not user_ids:
            return []
        setting_rows = await conn.fetch(
            "select * from availability_setting where user_id = any($1::uuid[])", user_ids
        )
        entry_rows = await conn.fetch(
            """
            select * from private_schedule_entry
            where user_id = any($1::uuid[])
              and start_date <= ($2::timestamptz at time zone time_zone)::date
              and coalesce(repeat_until, start_date) >=
                (($2::timestamptz at time zone time_zone)::date - 1)
            """,
            user_ids,
            now,
        )

    settings_by_user = {row["user_id"]: _settings(row, now) for row in setting_rows}
    entries_by_user: dict[UUID, list[BusyPeriod]] = defaultdict(list)
    for row in entry_rows:
        entries_by_user[row["user_id"]].append(_busy_period(row))
    return [
        FamilyAvailability(
            person_id=member["person_id"],
            display_name=member["display_name"],
            status=_derive_status(
                settings_by_user.get(member["user_id"]),
                entries_by_user[member["user_id"]],
                now,
            ),
            last_updated_at=now,
        )
        for member in members
    ]
