"""Bounded, family-scoped projection of existing historical records."""

from datetime import date, datetime
from datetime import time as Time
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_member
from app.db import pool
from app.routers.events import OCCURRENCE_CTES, EventCategory

router = APIRouter(prefix="/api", tags=["timeline"])

# Historical browsing remains arbitrary, but each query spans at most about ten years. This
# bounds the shared annual-event expansion to at most eleven projected years per source row.
MAX_RANGE_DAYS = 3_660
MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000

DatePrecision = Literal["day", "year", "unknown"]


class TimelineItemBase(BaseModel):
    item_key: str
    source_id: UUID
    title: str
    description: str | None
    relevant_date: date | None
    relevant_year: int | None
    date_precision: DatePrecision
    time: Time | None = None
    time_zone: str | None = None


class ImportantDateTimelineItem(TimelineItemBase):
    source_type: Literal["important_date"]
    category: EventCategory
    original_date: date
    repeats_annually: bool


class MemoryTimelineItem(TimelineItemBase):
    source_type: Literal["memory"]
    contributor_id: UUID
    contributor_name: str
    event_date: date
    published_at: datetime


class StoryTimelineItem(TimelineItemBase):
    source_type: Literal["story"]
    heirloom_id: UUID
    story_title: str
    story_version: int
    fact_id: UUID | None


TimelineItem = Annotated[
    ImportantDateTimelineItem | MemoryTimelineItem | StoryTimelineItem,
    Field(discriminator="source_type"),
]


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    limit: int
    offset: int
    next_offset: int | None


_SELECT = f"""
with {OCCURRENCE_CTES},
latest_stories as (
  select distinct on (s.heirloom_id)
    s.id, s.heirloom_id, s.version, s.title, s.dek, s.blocks
  from story s
  join heirloom h on h.id = s.heirloom_id
  left join story_request sr on sr.id = s.request_id
  where h.family_id = $1
    and s.status = 'published'
    and (s.request_id is null or sr.status = 'completed')
  order by s.heirloom_id, s.version desc, s.id
),
story_events as (
  select ls.*, event.value as event, event.ordinality as event_index
  from latest_stories ls
  cross join lateral (
    select value, ordinality
    from jsonb_path_query(
      ls.blocks, '$[*].events[*]'
    ) with ordinality as candidate(value, ordinality)
    where candidate.value ->> 'year' ~ '^[0-9]{{1,4}}$'
      and (candidate.value ->> 'year')::int between extract(year from $2::date)::int
                                                   and extract(year from $3::date)::int
      and candidate.value ->> 'fact_id' ~
        '^[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[1-5][0-9a-fA-F]{{3}}-[89abAB][0-9a-fA-F]{{3}}-[0-9a-fA-F]{{12}}$'
    limit $7
  ) event
),
items as (
  select
    'important_date:' || p.id || ':' || p.occurrence_date as item_key,
    'important_date'::text as source_type,
    p.id as source_id,
    p.title,
    p.description,
    p.occurrence_date as relevant_date,
    extract(year from p.occurrence_date)::int as relevant_year,
    'day'::text as date_precision,
    (p.event_at at time zone p.time_zone)::time as relevant_time,
    p.time_zone,
    p.category as event_category,
    p.event_date as original_date,
    p.repeats_annually,
    null::uuid as contributor_id,
    null::text as contributor_name,
    null::timestamptz as published_at,
    null::uuid as heirloom_id,
    null::text as story_title,
    null::int as story_version,
    null::uuid as fact_id
  from projected p
  where p.occurrence_date between $2 and $3

  union all

  select
    'memory:' || fm.id,
    'memory',
    fm.id,
    fm.title,
    fm.description,
    fm.event_date,
    extract(year from fm.event_date)::int,
    'day',
    null::time,
    null::text,
    null::text,
    null::date,
    null::boolean,
    fm.contributor_id,
    p.display_name,
    fm.published_at,
    null::uuid,
    null::text,
    null::int,
    null::uuid
  from family_memory fm
  join person p on p.id = fm.contributor_id
  join family_memory_photo cover_link
    on cover_link.memory_id = fm.id and cover_link.media_id = fm.cover_media_id
  join media cover on cover.id = fm.cover_media_id and cover.upload_status = 'ready'
  join media recording on recording.id = fm.recording_media_id
                      and recording.memory_id = fm.id
                      and recording.upload_status = 'ready'
  where fm.family_id = $1
    and fm.status = 'published'
    and fm.event_date between $2 and $3

  union all

  select
    'story:' || se.id || ':' || (se.event ->> 'fact_id') || ':'
      || se.event_index,
    'story',
    se.id,
    se.event ->> 'label',
    se.dek,
    null::date,
    (se.event ->> 'year')::int,
    'year',
    null::time,
    null::text,
    null::text,
    null::date,
    null::boolean,
    null::uuid,
    null::text,
    null::timestamptz,
    se.heirloom_id,
    se.title,
    se.version,
    (se.event ->> 'fact_id')::uuid
  from story_events se

  union all

  select
    'story:' || ls.id || ':unknown',
    'story',
    ls.id,
    ls.title,
    ls.dek,
    null::date,
    null::int,
    'unknown',
    null::time,
    null::text,
    null::text,
    null::date,
    null::boolean,
    null::uuid,
    null::text,
    null::timestamptz,
    ls.heirloom_id,
    ls.title,
    ls.version,
    null::uuid
  from latest_stories ls
  where $4
    and not exists (
      select 1
      from jsonb_path_query(
        ls.blocks, '$[*].events[*]'
      ) event(value)
      where event.value ->> 'year' ~ '^[0-9]{{1,4}}$'
        and event.value ->> 'fact_id' ~
          '^[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[1-5][0-9a-fA-F]{{3}}-[89abAB][0-9a-fA-F]{{3}}-[0-9a-fA-F]{{12}}$'
    )
)
select * from items
order by
  (relevant_year is null),
  relevant_year,
  case date_precision when 'year' then 0 else 1 end,
  relevant_date,
  relevant_time nulls first,
  lower(title),
  source_type,
  source_id,
  item_key
limit $5 offset $6
"""


def _item(row: asyncpg.Record) -> TimelineItem:
    common = {
        "item_key": row["item_key"],
        "source_id": row["source_id"],
        "title": row["title"],
        "description": row["description"],
        "relevant_date": row["relevant_date"],
        "relevant_year": row["relevant_year"],
        "date_precision": row["date_precision"],
        "time": row["relevant_time"],
        "time_zone": row["time_zone"],
    }
    if row["source_type"] == "important_date":
        return ImportantDateTimelineItem(
            **common,
            source_type="important_date",
            category=row["event_category"],
            original_date=row["original_date"],
            repeats_annually=row["repeats_annually"],
        )
    if row["source_type"] == "memory":
        return MemoryTimelineItem(
            **common,
            source_type="memory",
            contributor_id=row["contributor_id"],
            contributor_name=row["contributor_name"],
            event_date=row["relevant_date"],
            published_at=row["published_at"],
        )
    return StoryTimelineItem(
        **common,
        source_type="story",
        heirloom_id=row["heirloom_id"],
        story_title=row["story_title"],
        story_version=row["story_version"],
        fact_id=row["fact_id"],
    )


@router.get("/families/{family_id}/timeline")
async def list_timeline(
    family_id: UUID,
    start: date,
    end: date,
    user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
    include_unknown: bool = True,
) -> TimelinePage:
    if start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "start must be on or before end")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"timeline ranges cannot exceed {MAX_RANGE_DAYS} days",
        )
    if not 1 <= limit <= MAX_PAGE_SIZE or not 0 <= offset <= MAX_OFFSET:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid pagination")

    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        rows = await conn.fetch(
            _SELECT,
            family_id,
            start,
            end,
            include_unknown,
            limit + 1,
            offset,
            offset + limit + 1,
        )
    has_more = len(rows) > limit
    items = [_item(row) for row in rows[:limit]]
    return TimelinePage(
        items=items,
        limit=limit,
        offset=offset,
        next_offset=offset + limit if has_more else None,
    )
