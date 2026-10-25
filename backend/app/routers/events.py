"""Family Important Dates: bounded calendar projection and creator-owned CRUD."""

from datetime import UTC, datetime
from datetime import date as Date
from datetime import time as Time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth import CurrentUser, require_member
from app.db import pool

router = APIRouter(prefix="/api", tags=["important-dates"])

EventCategory = Literal["birthday", "anniversary", "family_function", "cultural_function", "other"]
MAX_RANGE_DAYS = 366
MAX_RELATED_PEOPLE = 50

# Shared by the calendar and timeline projections so annual events, including the
# February 29 fallback, have exactly one recurrence rule everywhere.
OCCURRENCE_CTES = """
years(year) as (
  select generate_series(
    extract(year from $2::date)::int,
    extract(year from $3::date)::int
  )
), projected as (
  select e.*,
    case
      when not e.repeats_annually then e.event_date
      when extract(month from e.event_date) = 2
        and extract(day from e.event_date) = 29
        and not (years.year % 4 = 0 and (years.year % 100 != 0 or years.year % 400 = 0))
        then make_date(years.year, 2, 28)
      else make_date(
        years.year,
        extract(month from e.event_date)::int,
        extract(day from e.event_date)::int
      )
    end as occurrence_date
  from family_event e cross join years
  where e.family_id = $1
    and (e.repeats_annually or years.year = extract(year from e.event_date)::int)
)
"""


class EventValues(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    category: EventCategory
    date: Date
    time: Time | None = None
    time_zone: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    related_person_ids: list[UUID] = Field(default_factory=list, max_length=MAX_RELATED_PEOPLE)
    repeats_annually: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title cannot be blank")
        return value

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("related_person_ids")
    @classmethod
    def unique_people(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("related people must be unique")
        return value

    @model_validator(mode="after")
    def valid_time_and_recurrence(self):
        if (self.time is None) != (self.time_zone is None):
            raise ValueError("time and time_zone must be provided together")
        if self.time is not None and self.time.tzinfo is not None:
            raise ValueError("time must be local; provide its IANA time_zone separately")
        if self.time_zone is not None:
            try:
                zone = ZoneInfo(self.time_zone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("time_zone must be a valid IANA time zone") from exc
            local = datetime.combine(self.date, self.time, zone)
            round_trip = local.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
            if round_trip != datetime.combine(self.date, self.time):
                raise ValueError("time does not exist in that time zone on this date")
        if self.category == "cultural_function" and self.repeats_annually:
            raise ValueError("cultural functions need explicit occurrence dates")
        return self


class CreateEvent(EventValues):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class UpdateEvent(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: EventCategory | None = None
    date: Date | None = None
    time: Time | None = None
    time_zone: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    related_person_ids: list[UUID] | None = Field(default=None, max_length=MAX_RELATED_PEOPLE)
    repeats_annually: bool | None = None


class FamilyEvent(EventValues):
    id: UUID
    family_id: UUID
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class EventOccurrence(FamilyEvent):
    occurrence_date: Date
    occurrence_at: datetime | None = None


def _instant(values: EventValues) -> datetime | None:
    if values.time is None or values.time_zone is None:
        return None
    return datetime.combine(values.date, values.time, ZoneInfo(values.time_zone)).astimezone(UTC)


def _local_time(event_at: datetime | None, time_zone: str | None) -> Time | None:
    if event_at is None or time_zone is None:
        return None
    return event_at.astimezone(ZoneInfo(time_zone)).time().replace(tzinfo=None)


def _event(row: asyncpg.Record) -> FamilyEvent:
    return FamilyEvent(
        id=row["id"],
        family_id=row["family_id"],
        created_by=row["created_by"],
        title=row["title"],
        category=row["category"],
        date=row["event_date"],
        time=_local_time(row["event_at"], row["time_zone"]),
        time_zone=row["time_zone"],
        description=row["description"],
        related_person_ids=list(row["related_person_ids"]),
        repeats_annually=row["repeats_annually"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _occurrence(row: asyncpg.Record) -> EventOccurrence:
    event = _event(row)
    occurrence_at = None
    if event.time is not None and event.time_zone is not None:
        occurrence_at = datetime.combine(
            row["occurrence_date"], event.time, ZoneInfo(event.time_zone)
        )
    return EventOccurrence(
        **event.model_dump(), occurrence_date=row["occurrence_date"], occurrence_at=occurrence_at
    )


_SELECT = """
    select e.*,
           array(select ep.person_id from family_event_person ep
                 where ep.event_id = e.id order by ep.person_id) as related_person_ids
    from family_event e
"""


async def _get(conn: asyncpg.Connection, event_id: UUID, *, lock: bool = False) -> FamilyEvent:
    suffix = " for update" if lock else ""
    row = await conn.fetchrow(_SELECT + " where e.id = $1" + suffix, event_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return _event(row)


async def _check_people(conn: asyncpg.Connection, family_id: UUID, person_ids: list[UUID]) -> None:
    if not person_ids:
        return
    count = await conn.fetchval(
        "select count(*) from person where family_id = $1 and id = any($2::uuid[])",
        family_id,
        person_ids,
    )
    if count != len(person_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "every related person must belong to this family",
        )


async def _replace_people(
    conn: asyncpg.Connection, event_id: UUID, family_id: UUID, person_ids: list[UUID]
) -> None:
    await conn.execute("delete from family_event_person where event_id = $1", event_id)
    if person_ids:
        await conn.executemany(
            "insert into family_event_person (event_id, family_id, person_id) values ($1, $2, $3)",
            [(event_id, family_id, person_id) for person_id in person_ids],
        )


@router.get("/families/{family_id}/events")
async def list_events(
    family_id: UUID,
    start: Date,
    end: Date,
    user: CurrentUser,
    limit: int = 100,
    offset: int = 0,
) -> list[EventOccurrence]:
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start must be on or before end")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"calendar ranges cannot exceed {MAX_RANGE_DAYS} days",
        )
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid pagination")
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        rows = await conn.fetch(
            f"""
            with {OCCURRENCE_CTES}
            select p.*,
              array(select ep.person_id from family_event_person ep
                    where ep.event_id = p.id order by ep.person_id) as related_person_ids
            from projected p
            where p.occurrence_date between $2 and $3
            order by p.occurrence_date,
              (p.event_at at time zone p.time_zone)::time nulls first,
              lower(p.title), p.id
            limit $4 offset $5
            """,
            family_id,
            start,
            end,
            limit,
            offset,
        )
    return [_occurrence(row) for row in rows]


@router.get("/events/{event_id}")
async def get_event(event_id: UUID, user: CurrentUser) -> FamilyEvent:
    async with pool().acquire() as conn:
        event = await _get(conn, event_id)
        await require_member(conn, user, event.family_id)
    return event


@router.post(
    "/families/{family_id}/events",
    status_code=status.HTTP_201_CREATED,
)
async def create_event(family_id: UUID, body: CreateEvent, user: CurrentUser) -> FamilyEvent:
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        await _check_people(conn, family_id, body.related_person_ids)
        async with conn.transaction():
            event_id = await conn.fetchval(
                """
                insert into family_event
                  (family_id, created_by, title, category, event_date, event_at, time_zone,
                   description, repeats_annually, idempotency_key)
                values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                on conflict (created_by, idempotency_key) where idempotency_key is not null
                  do nothing
                returning id
                """,
                family_id,
                user.id,
                body.title,
                body.category,
                body.date,
                _instant(body),
                body.time_zone,
                body.description,
                body.repeats_annually,
                body.idempotency_key,
            )
            if event_id is None:
                existing = await conn.fetchrow(
                    "select id, family_id from family_event "
                    "where created_by = $1 and idempotency_key = $2",
                    user.id,
                    body.idempotency_key,
                )
                if existing["family_id"] != family_id:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "idempotency key was already used in another family",
                    )
                return await _get(conn, existing["id"])
            await _replace_people(conn, event_id, family_id, body.related_person_ids)
        return await _get(conn, event_id)


@router.patch("/events/{event_id}")
async def update_event(event_id: UUID, body: UpdateEvent, user: CurrentUser) -> FamilyEvent:
    if not body.model_fields_set:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide at least one change")
    async with pool().acquire() as conn, conn.transaction():
        current = await _get(conn, event_id, lock=True)
        await require_member(conn, user, current.family_id)
        if current.created_by != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only the event creator can edit it")

        values = current.model_dump(
            include={
                "title",
                "category",
                "date",
                "time",
                "time_zone",
                "description",
                "related_person_ids",
                "repeats_annually",
            }
        )
        for field in body.model_fields_set:
            values[field] = getattr(body, field)
        if "time" in body.model_fields_set and body.time is None:
            values["time_zone"] = None
        try:
            changed = CreateEvent.model_validate(values)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        await _check_people(conn, current.family_id, changed.related_person_ids)
        await conn.execute(
            """
            update family_event set title = $2, category = $3, event_date = $4,
              event_at = $5, time_zone = $6, description = $7, repeats_annually = $8,
              updated_at = now()
            where id = $1
            """,
            event_id,
            changed.title,
            changed.category,
            changed.date,
            _instant(changed),
            changed.time_zone,
            changed.description,
            changed.repeats_annually,
        )
        await _replace_people(conn, event_id, current.family_id, changed.related_person_ids)
        return await _get(conn, event_id)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: UUID, user: CurrentUser) -> Response:
    async with pool().acquire() as conn, conn.transaction():
        event = await _get(conn, event_id, lock=True)
        await require_member(conn, user, event.family_id)
        if event.created_by != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only the event creator can delete it")
        await conn.execute("delete from family_event where id = $1", event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
