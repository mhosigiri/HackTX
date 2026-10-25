"""Family photo memories and the legacy heirloom memory-note contribution route."""

import asyncio
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from app import storage
from app.auth import CurrentUser, User, family_of_heirloom, require_member
from app.db import pool
from app.jobs.queue import enqueue
from app.routers.notifications import create_notification

router = APIRouter(prefix="/api", tags=["memories"])

MemoryStatus = Literal["draft", "published"]
UploadKind = Literal["photo", "audio"]
MAX_PAGE_SIZE = 50
MAX_PHOTOS = 20
MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_AUDIO_BYTES = 50 * 1024 * 1024
PHOTO_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
AUDIO_MIMES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/mpeg"}


class NewMemory(BaseModel):
    text: str = Field(min_length=1)


class MemoryNote(BaseModel):
    id: UUID
    heirloom_id: UUID
    author_id: UUID
    text: str | None


class MemoryMetadata(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    event_date: date | None = None
    language: str = Field(default="en", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

    @field_validator("title", "description")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CreateFamilyMemory(MemoryMetadata):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class UpdateFamilyMemory(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    event_date: date | None = None
    language: str | None = Field(default=None, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

    @field_validator("title", "description")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return MemoryMetadata.clean_optional_text(value)

    @field_validator("language")
    @classmethod
    def language_cannot_be_cleared(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("language cannot be null")
        return value


class MemoryMedia(BaseModel):
    id: UUID
    mime: str
    byte_size: int
    url: str


class MemoryPhoto(MemoryMedia):
    position: int


class FamilyMemorySummary(BaseModel):
    id: UUID
    family_id: UUID
    contributor_id: UUID
    contributor_name: str
    title: str | None
    event_date: date | None
    status: MemoryStatus
    cover_url: str | None
    audio_url: str | None
    published_at: datetime | None
    updated_at: datetime


class FamilyMemoryDetail(FamilyMemorySummary):
    description: str | None
    language: str
    photos: list[MemoryPhoto]
    recording: MemoryMedia | None
    created_at: datetime


class CreateUpload(BaseModel):
    kind: UploadKind
    mime: str = Field(min_length=1, max_length=100)
    byte_size: int = Field(gt=0)

    @field_validator("mime")
    @classmethod
    def normalize_mime(cls, value: str) -> str:
        return value.split(";", 1)[0].strip().lower()


class MemoryUpload(BaseModel):
    media_id: UUID
    upload_url: str
    upload_status: Literal["uploading", "failed"] = "uploading"


class AttachPhoto(BaseModel):
    media_id: UUID


class ReorderPhotos(BaseModel):
    media_ids: list[UUID] = Field(min_length=1, max_length=MAX_PHOTOS)

    @field_validator("media_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("media_ids must be unique")
        return value


def _validate_upload(kind: UploadKind, mime: str, byte_size: int) -> None:
    allowed = PHOTO_MIMES if kind == "photo" else AUDIO_MIMES
    limit = MAX_PHOTO_BYTES if kind == "photo" else MAX_AUDIO_BYTES
    if mime not in allowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unsupported {kind} type")
    if byte_size > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"{kind} cannot exceed {limit // (1024 * 1024)} MB",
        )


async def _reserved_photo_count(conn: asyncpg.Connection, memory_id: UUID) -> int:
    return await conn.fetchval(
        """
        select
          (select count(*) from family_memory_photo where memory_id = $1)
          +
          (select count(*) from media m
           where m.memory_id = $1 and m.kind = 'photo'
             and not exists (
               select 1 from family_memory_photo mp
               where mp.memory_id = $1 and mp.media_id = m.id
             ))
        """,
        memory_id,
    )


async def _has_external_media_reference(
    conn: asyncpg.Connection, media_id: UUID, memory_id: UUID
) -> bool:
    """Protect every reference outside the family memory currently being deleted."""
    return await conn.fetchval(
        """
        select
          exists(select 1 from media where id = $1 and heirloom_id is not null)
          or exists(select 1 from heirloom where cover_media_id = $1)
          or exists(select 1 from person where avatar_media_id = $1)
          or exists(select 1 from profile where avatar_media_id = $1)
          or exists(select 1 from turn where audio_media_id = $1)
          or exists(select 1 from memory_note where audio_media_id = $1)
          or exists(select 1 from story where recording_media_id = $1)
          or exists(select 1 from story_request where capture_media_id = $1)
          or exists(
            select 1 from family_memory
            where id <> $2 and (cover_media_id = $1 or recording_media_id = $1)
          )
          or exists(
            select 1 from family_memory_photo where memory_id <> $2 and media_id = $1
          )
        """,
        media_id,
        memory_id,
    )


async def _memory_row(
    conn: asyncpg.Connection, memory_id: UUID, user: User, *, edit: bool = False, lock: bool = False
) -> asyncpg.Record:
    suffix = " for update of fm" if lock else ""
    row = await conn.fetchrow(
        """
        select fm.*, p.display_name as contributor_name,
               cover.storage_path as cover_path,
               recording.storage_path as recording_path,
               recording.mime as recording_mime,
               recording.byte_size as recording_size
        from family_memory fm
        join person p on p.id = fm.contributor_id
        left join media cover on cover.id = fm.cover_media_id and cover.upload_status = 'ready'
        left join media recording
          on recording.id = fm.recording_media_id and recording.upload_status = 'ready'
        where fm.id = $1
        """
        + suffix,
        memory_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    await require_member(conn, user, row["family_id"])
    if row["created_by"] != user.id and (edit or row["status"] == "draft"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    return row


async def _media_url(kind: UploadKind, path: str | None) -> str | None:
    if path is None:
        return None
    bucket: storage.Bucket = "photos" if kind == "photo" else "audio"
    return await storage.signed_download_url(bucket, path)


async def _summary(row: asyncpg.Record) -> FamilyMemorySummary:
    cover_url, audio_url = await asyncio.gather(
        _media_url("photo", row["cover_path"]), _media_url("audio", row["recording_path"])
    )
    return FamilyMemorySummary(
        id=row["id"],
        family_id=row["family_id"],
        contributor_id=row["contributor_id"],
        contributor_name=row["contributor_name"],
        title=row["title"],
        event_date=row["event_date"],
        status=row["status"],
        cover_url=cover_url,
        audio_url=audio_url,
        published_at=row["published_at"],
        updated_at=row["updated_at"],
    )


async def _detail(conn: asyncpg.Connection, row: asyncpg.Record) -> FamilyMemoryDetail:
    photos = await conn.fetch(
        """
        select m.id, m.mime, m.byte_size, m.storage_path, mp.position
        from family_memory_photo mp join media m on m.id = mp.media_id
        where mp.memory_id = $1 and m.upload_status = 'ready' order by mp.position
        """,
        row["id"],
    )
    urls = await asyncio.gather(*[_media_url("photo", item["storage_path"]) for item in photos])
    summary = await _summary(row)
    recording = None
    if row["recording_path"] is not None:
        recording = MemoryMedia(
            id=row["recording_media_id"],
            mime=row["recording_mime"],
            byte_size=row["recording_size"],
            url=summary.audio_url,
        )
    return FamilyMemoryDetail(
        **summary.model_dump(),
        description=row["description"],
        language=row["language"],
        photos=[
            MemoryPhoto(
                id=item["id"],
                mime=item["mime"],
                byte_size=item["byte_size"],
                position=item["position"],
                url=url,
            )
            for item, url in zip(photos, urls, strict=True)
        ],
        recording=recording,
        created_at=row["created_at"],
    )


@router.post("/heirlooms/{heirloom_id}/memories", status_code=status.HTTP_201_CREATED)
async def add_memory(heirloom_id: UUID, body: NewMemory, user: CurrentUser) -> MemoryNote:
    """Preserve the existing heirloom contribution and its protected pipeline trigger."""
    async with pool().acquire() as conn:
        family_id = await family_of_heirloom(conn, heirloom_id)
        author_id = await require_member(conn, user, family_id)
        async with conn.transaction():
            row = await conn.fetchrow(
                "insert into memory_note (heirloom_id, author_id, text) values ($1, $2, $3) "
                "returning id, heirloom_id, author_id, text",
                heirloom_id,
                author_id,
                body.text,
            )
            await enqueue(conn, "extract_facts", heirloom_id, family_id)
    return MemoryNote(**row)


@router.post("/families/{family_id}/memories", status_code=status.HTTP_201_CREATED)
async def create_family_memory(
    family_id: UUID, body: CreateFamilyMemory, user: CurrentUser
) -> FamilyMemoryDetail:
    async with pool().acquire() as conn, conn.transaction():
        contributor_id = await require_member(conn, user, family_id)
        if body.idempotency_key:
            await conn.execute(
                "select pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"family-memory:{user.id}:{body.idempotency_key}",
            )
            existing = await conn.fetchval(
                "select id from family_memory where created_by = $1 and idempotency_key = $2",
                user.id,
                body.idempotency_key,
            )
            if existing:
                row = await _memory_row(conn, existing, user)
                if row["family_id"] != family_id:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "idempotency key was already used in another family",
                    )
                return await _detail(conn, row)
        memory_id = await conn.fetchval(
            """
            insert into family_memory
              (family_id, contributor_id, created_by, title, description, event_date, language,
               idempotency_key)
            values ($1, $2, $3, $4, $5, $6, $7, $8) returning id
            """,
            family_id,
            contributor_id,
            user.id,
            body.title,
            body.description,
            body.event_date,
            body.language,
            body.idempotency_key,
        )
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.get("/families/{family_id}/memories")
async def list_family_memories(
    family_id: UUID,
    user: CurrentUser,
    limit: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Field(ge=0, le=10_000)] = 0,
    include_my_drafts: bool = False,
) -> list[FamilyMemorySummary]:
    if not 1 <= limit <= MAX_PAGE_SIZE or not 0 <= offset <= 10_000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid pagination")
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        rows = await conn.fetch(
            """
            select fm.*, p.display_name as contributor_name,
                   cover.storage_path as cover_path,
                   recording.storage_path as recording_path,
                   recording.mime as recording_mime,
                   recording.byte_size as recording_size
            from family_memory fm
            join person p on p.id = fm.contributor_id
            left join media cover
              on cover.id = fm.cover_media_id and cover.upload_status = 'ready'
            left join media recording
              on recording.id = fm.recording_media_id and recording.upload_status = 'ready'
            where fm.family_id = $1
              and (fm.status = 'published' or ($4 and fm.created_by = $2))
            order by coalesce(fm.published_at, fm.updated_at) desc, fm.id desc
            limit $3 offset $5
            """,
            family_id,
            user.id,
            limit,
            include_my_drafts,
            offset,
        )
    return list(await asyncio.gather(*[_summary(row) for row in rows]))


@router.get("/memories/{memory_id}")
async def get_family_memory(memory_id: UUID, user: CurrentUser) -> FamilyMemoryDetail:
    async with pool().acquire() as conn:
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.patch("/memories/{memory_id}")
async def update_family_memory(
    memory_id: UUID, body: UpdateFamilyMemory, user: CurrentUser
) -> FamilyMemoryDetail:
    if not body.model_fields_set:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide at least one change")
    async with pool().acquire() as conn, conn.transaction():
        current = await _memory_row(conn, memory_id, user, edit=True, lock=True)
        values = {
            "title": current["title"],
            "description": current["description"],
            "event_date": current["event_date"],
            "language": current["language"],
        }
        for field in body.model_fields_set:
            values[field] = getattr(body, field)
        if current["status"] == "published" and not values["title"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "published title is required"
            )
        await conn.execute(
            """
            update family_memory set title = $2, description = $3, event_date = $4,
              language = $5, updated_at = now() where id = $1
            """,
            memory_id,
            values["title"],
            values["description"],
            values["event_date"],
            values["language"],
        )
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.post("/memories/{memory_id}/media", status_code=status.HTTP_201_CREATED)
async def create_memory_upload(
    memory_id: UUID, body: CreateUpload, user: CurrentUser
) -> MemoryUpload:
    _validate_upload(body.kind, body.mime, body.byte_size)
    media_id = uuid4()
    async with pool().acquire() as conn, conn.transaction():
        memory = await _memory_row(conn, memory_id, user, edit=True, lock=True)
        if body.kind == "photo":
            if await _reserved_photo_count(conn, memory_id) >= MAX_PHOTOS:
                raise HTTPException(status.HTTP_409_CONFLICT, "memory already has 20 photos")
        else:
            exists = await conn.fetchval(
                "select 1 from media where memory_id = $1 and kind = 'audio' "
                "and upload_status in ('uploading', 'ready')",
                memory_id,
            )
            if exists or memory["recording_media_id"] is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "memory already has a recording")
        path = storage.object_path(memory["family_id"], memory_id, media_id, body.mime)
        await conn.execute(
            """
            insert into media
              (id, family_id, memory_id, kind, storage_path, mime, byte_size, created_by,
               upload_status)
            values ($1, $2, $3, $4, $5, $6, $7, $8, 'uploading')
            """,
            media_id,
            memory["family_id"],
            memory_id,
            body.kind,
            path,
            body.mime,
            body.byte_size,
            user.id,
        )
    bucket: storage.Bucket = "photos" if body.kind == "photo" else "audio"
    return MemoryUpload(media_id=media_id, upload_url=await storage.signed_upload_url(bucket, path))


@router.post("/memories/{memory_id}/media/{media_id}/upload-url")
async def retry_memory_upload(memory_id: UUID, media_id: UUID, user: CurrentUser) -> MemoryUpload:
    async with pool().acquire() as conn, conn.transaction():
        await _memory_row(conn, memory_id, user, edit=True)
        media = await conn.fetchrow(
            "select kind, storage_path, upload_status from media "
            "where id = $1 and memory_id = $2 and created_by = $3",
            media_id,
            memory_id,
            user.id,
        )
        if media is None or media["upload_status"] == "ready":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "pending upload not found")
        bucket: storage.Bucket = "photos" if media["kind"] == "photo" else "audio"
        if media["upload_status"] == "failed":
            await storage.delete_objects(bucket, [media["storage_path"]])
        await conn.execute("update media set upload_status = 'uploading' where id = $1", media_id)
    url = await storage.signed_upload_url(bucket, media["storage_path"])
    return MemoryUpload(media_id=media_id, upload_url=url)


@router.post("/memories/{memory_id}/media/{media_id}/complete")
async def complete_memory_upload(
    memory_id: UUID, media_id: UUID, user: CurrentUser
) -> FamilyMemoryDetail:
    async with pool().acquire() as conn:
        await _memory_row(conn, memory_id, user, edit=True)
        media = await conn.fetchrow(
            "select * from media where id = $1 and memory_id = $2 and created_by = $3",
            media_id,
            memory_id,
            user.id,
        )
        if media is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")
        if media["upload_status"] == "ready":
            return await _detail(conn, await _memory_row(conn, memory_id, user))
        if media["upload_status"] not in ("uploading", "failed"):
            raise HTTPException(status.HTTP_409_CONFLICT, "upload cannot be completed")
    bucket: storage.Bucket = "photos" if media["kind"] == "photo" else "audio"
    info = await storage.object_info(bucket, media["storage_path"])
    if info is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "upload has not completed; retry it")
    try:
        _validate_upload(media["kind"], info.mime, info.byte_size)
        if info.mime != media["mime"] or info.byte_size != media["byte_size"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "uploaded object does not match the declared type and size",
            )
    except HTTPException:
        async with pool().acquire() as conn:
            await conn.execute("update media set upload_status = 'failed' where id = $1", media_id)
        raise

    async with pool().acquire() as conn, conn.transaction():
        memory = await _memory_row(conn, memory_id, user, edit=True, lock=True)
        media = await conn.fetchrow(
            "select * from media where id = $1 and memory_id = $2 and created_by = $3 for update",
            media_id,
            memory_id,
            user.id,
        )
        if media is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")
        if media["upload_status"] == "ready":
            return await _detail(conn, await _memory_row(conn, memory_id, user))
        if media["kind"] == "photo":
            position = await conn.fetchval(
                "select coalesce(max(position), -1) + 1 from family_memory_photo "
                "where memory_id = $1",
                memory_id,
            )
            if position >= MAX_PHOTOS:
                raise HTTPException(status.HTTP_409_CONFLICT, "memory already has 20 photos")
            await conn.execute(
                "insert into family_memory_photo (memory_id, media_id, position) "
                "values ($1, $2, $3)",
                memory_id,
                media_id,
                position,
            )
            await conn.execute(
                "update family_memory set cover_media_id = coalesce(cover_media_id, $2), "
                "updated_at = now() where id = $1",
                memory_id,
                media_id,
            )
        else:
            if memory["recording_media_id"] not in (None, media_id):
                raise HTTPException(status.HTTP_409_CONFLICT, "memory already has a recording")
            await conn.execute(
                "update family_memory set recording_media_id = $2, updated_at = now() "
                "where id = $1",
                memory_id,
                media_id,
            )
        await conn.execute(
            "update media set upload_status = 'ready', byte_size = $2 where id = $1",
            media_id,
            info.byte_size,
        )
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.post("/memories/{memory_id}/photos")
async def attach_existing_photo(
    memory_id: UUID, body: AttachPhoto, user: CurrentUser
) -> FamilyMemoryDetail:
    async with pool().acquire() as conn, conn.transaction():
        await _memory_row(conn, memory_id, user, edit=True, lock=True)
        media = await conn.fetchrow(
            """
            select id, storage_path, mime, byte_size from media
            where id = $1 and family_id = (select family_id from family_memory where id = $2)
              and created_by = $3 and kind = 'photo' and upload_status = 'ready'
              and memory_id is null
            """,
            body.media_id,
            memory_id,
            user.id,
        )
        if media is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "selectable photo not found")
        info = await storage.object_info("photos", media["storage_path"])
        if info is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "selected photo is missing from storage")
        _validate_upload("photo", info.mime, info.byte_size)
        if info.mime != media["mime"] or (
            media["byte_size"] is not None and info.byte_size != media["byte_size"]
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "selected photo does not match its saved metadata",
            )
        await conn.execute(
            "update media set byte_size = $2 where id = $1", body.media_id, info.byte_size
        )
        existing = await conn.fetchval(
            "select 1 from family_memory_photo where memory_id = $1 and media_id = $2",
            memory_id,
            body.media_id,
        )
        if existing:
            return await _detail(conn, await _memory_row(conn, memory_id, user))
        if await _reserved_photo_count(conn, memory_id) >= MAX_PHOTOS:
            raise HTTPException(status.HTTP_409_CONFLICT, "memory already has 20 photos")
        position = await conn.fetchval(
            "select coalesce(max(position), -1) + 1 from family_memory_photo where memory_id = $1",
            memory_id,
        )
        await conn.execute(
            "insert into family_memory_photo (memory_id, media_id, position) values ($1, $2, $3) "
            "on conflict (memory_id, media_id) do nothing",
            memory_id,
            body.media_id,
            position,
        )
        await conn.execute(
            "update family_memory set cover_media_id = coalesce(cover_media_id, $2), "
            "updated_at = now() where id = $1",
            memory_id,
            body.media_id,
        )
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.put("/memories/{memory_id}/photos/order")
async def reorder_memory_photos(
    memory_id: UUID, body: ReorderPhotos, user: CurrentUser
) -> FamilyMemoryDetail:
    async with pool().acquire() as conn, conn.transaction():
        await _memory_row(conn, memory_id, user, edit=True, lock=True)
        current = await conn.fetch(
            "select media_id from family_memory_photo where memory_id = $1", memory_id
        )
        if {row["media_id"] for row in current} != set(body.media_ids):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "media_ids must contain every attached photo exactly once",
            )
        await conn.execute("delete from family_memory_photo where memory_id = $1", memory_id)
        await conn.executemany(
            "insert into family_memory_photo (memory_id, media_id, position) values ($1, $2, $3)",
            [(memory_id, media_id, position) for position, media_id in enumerate(body.media_ids)],
        )
        await conn.execute(
            "update family_memory set cover_media_id = $2, updated_at = now() where id = $1",
            memory_id,
            body.media_ids[0],
        )
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.post("/memories/{memory_id}/publish")
async def publish_family_memory(memory_id: UUID, user: CurrentUser) -> FamilyMemoryDetail:
    async with pool().acquire() as conn, conn.transaction():
        memory = await _memory_row(conn, memory_id, user, edit=True, lock=True)
        photo_count = await conn.fetchval(
            """
            select count(*) from family_memory_photo mp join media m on m.id = mp.media_id
            where mp.memory_id = $1 and m.kind = 'photo' and m.upload_status = 'ready'
            """,
            memory_id,
        )
        recording_ok = await conn.fetchval(
            "select 1 from media where id = $1 and memory_id = $2 and kind = 'audio' "
            "and upload_status = 'ready'",
            memory["recording_media_id"],
            memory_id,
        )
        if not memory["title"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "title is required")
        if photo_count < 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "a photo is required")
        if not recording_ok:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "a completed recording is required"
            )
        await conn.execute(
            """
            update family_memory set status = 'published',
              published_at = coalesce(published_at, now()),
              updated_at = now() where id = $1
            """,
            memory_id,
        )
        recipients = await conn.fetch(
            "select distinct person_id from member "
            "where family_id = $1 and person_id is not null and person_id <> $2",
            memory["family_id"],
            memory["contributor_id"],
        )
        for recipient in recipients:
            await create_notification(
                conn,
                ntype="memory_added",
                recipient_id=recipient["person_id"],
                memory_id=memory_id,
            )
        return await _detail(conn, await _memory_row(conn, memory_id, user))


@router.delete("/memories/{memory_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_media(memory_id: UUID, media_id: UUID, user: CurrentUser) -> Response:
    async with pool().acquire() as conn, conn.transaction():
        memory = await _memory_row(conn, memory_id, user, edit=True, lock=True)
        media = await conn.fetchrow(
            """
            select m.*,
              exists(select 1 from family_memory_photo mp
                     where mp.memory_id = $1 and mp.media_id = m.id) as is_photo,
              ($2 = m.id) as is_recording
            from media m where m.id = $3
              and (m.memory_id = $1 or exists(
                select 1 from family_memory_photo mp where mp.memory_id = $1 and mp.media_id = m.id
              ))
            for update of m
            """,
            memory_id,
            memory["recording_media_id"],
            media_id,
        )
        if media is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "attachment not found")
        if memory["status"] == "published":
            if media["is_recording"]:
                raise HTTPException(status.HTTP_409_CONFLICT, "published recording is required")
            count = await conn.fetchval(
                "select count(*) from family_memory_photo where memory_id = $1", memory_id
            )
            if media["is_photo"] and count <= 1:
                raise HTTPException(status.HTTP_409_CONFLICT, "published photo is required")
        if media["memory_id"] == memory_id:
            if await _has_external_media_reference(conn, media_id, memory_id):
                raise HTTPException(status.HTTP_409_CONFLICT, "media is still used elsewhere")
            bucket: storage.Bucket = "photos" if media["kind"] == "photo" else "audio"
            await storage.delete_objects(bucket, [media["storage_path"]])
        if media["is_recording"]:
            await conn.execute(
                "update family_memory set recording_media_id = null, updated_at = now() "
                "where id = $1",
                memory_id,
            )
        if media["is_photo"]:
            await conn.execute(
                "delete from family_memory_photo where memory_id = $1 and media_id = $2",
                memory_id,
                media_id,
            )
            if memory["cover_media_id"] == media_id:
                next_cover = await conn.fetchval(
                    "select media_id from family_memory_photo where memory_id = $1 "
                    "order by position limit 1",
                    memory_id,
                )
                await conn.execute(
                    "update family_memory set cover_media_id = $2, updated_at = now() "
                    "where id = $1",
                    memory_id,
                    next_cover,
                )
        if media["memory_id"] == memory_id:
            await conn.execute("delete from media where id = $1", media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_memory(memory_id: UUID, user: CurrentUser) -> Response:
    async with pool().acquire() as conn, conn.transaction():
        await _memory_row(conn, memory_id, user, edit=True, lock=True)
        media = await conn.fetch(
            "select id, kind, storage_path from media where memory_id = $1 for update", memory_id
        )
        for item in media:
            if await _has_external_media_reference(conn, item["id"], memory_id):
                raise HTTPException(status.HTTP_409_CONFLICT, "media is still used elsewhere")
        await storage.delete_objects(
            "photos", [row["storage_path"] for row in media if row["kind"] == "photo"]
        )
        await storage.delete_objects(
            "audio", [row["storage_path"] for row in media if row["kind"] == "audio"]
        )
        await conn.execute(
            "update family_memory set status = 'draft', cover_media_id = null, "
            "recording_media_id = null, published_at = null where id = $1",
            memory_id,
        )
        await conn.execute("delete from family_memory where id = $1", memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
