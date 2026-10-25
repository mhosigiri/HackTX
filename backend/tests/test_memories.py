"""Family-memory drafts, media integrity, publication, authorization, and storage privacy."""

from datetime import date
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from app import storage
from app.auth import User
from app.routers import memories
from app.routers.memories import (
    AttachPhoto,
    CreateFamilyMemory,
    CreateUpload,
    ReorderPhotos,
    UpdateFamilyMemory,
)


async def add_member(conn, family_id: UUID, name: str) -> tuple[UUID, UUID]:
    user_id, person_id = uuid4(), uuid4()
    await conn.execute("insert into auth.users (id) values ($1)", user_id)
    await conn.execute(
        "insert into person (id, family_id, display_name) values ($1, $2, $3)",
        person_id,
        family_id,
        name,
    )
    await conn.execute(
        "insert into member (user_id, family_id, person_id) values ($1, $2, $3)",
        user_id,
        family_id,
        person_id,
    )
    return user_id, person_id


async def add_other_family(conn) -> tuple[UUID, UUID, UUID]:
    family_id = await conn.fetchval(
        "insert into family (name, invite_code) values ('Other', $1) returning id", str(uuid4())
    )
    user_id, person_id = await add_member(conn, family_id, "Outsider")
    return family_id, user_id, person_id


async def upload(conn, fakes, memory_id, user_id, kind, mime, data):
    pending = await memories.create_memory_upload(
        memory_id,
        CreateUpload(kind=kind, mime=mime, byte_size=len(data)),
        User(id=user_id),
    )
    path = await conn.fetchval("select storage_path from media where id = $1", pending.media_id)
    fakes.files[path] = data
    fakes.file_mimes[path] = mime
    detail = await memories.complete_memory_upload(memory_id, pending.media_id, User(id=user_id))
    return pending.media_id, path, detail


async def published_memory(conn, fakes, seed, *, title="Summer picnic"):
    draft = await memories.create_family_memory(
        seed.family_id,
        CreateFamilyMemory(title=title, description="By the lake", language="en-US"),
        User(id=seed.user_id),
    )
    photo_id, photo_path, _ = await upload(
        conn, fakes, draft.id, seed.user_id, "photo", "image/jpeg", b"photo"
    )
    audio_id, audio_path, _ = await upload(
        conn, fakes, draft.id, seed.user_id, "audio", "audio/wav", b"RIFF-memory"
    )
    detail = await memories.publish_family_memory(draft.id, User(id=seed.user_id))
    return detail, photo_id, audio_id, photo_path, audio_path


async def visible(conn, user_id: UUID, sql: str, *args) -> int:
    async with conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", str(user_id))
        count = await conn.fetchval(sql, *args)
        await conn.execute("reset role")
    return count


async def test_drafts_are_owner_only_and_family_lists_are_bounded(conn, fakes, seed):
    relative, _ = await add_member(conn, seed.family_id, "Relative")
    _, outsider, _ = await add_other_family(conn)
    owner = User(id=seed.user_id)
    draft = await memories.create_family_memory(
        seed.family_id,
        CreateFamilyMemory(
            title="  Childhood home  ",
            event_date=date(1999, 12, 31),
            idempotency_key="memory-create-1",
        ),
        owner,
    )
    repeated = await memories.create_family_memory(
        seed.family_id,
        CreateFamilyMemory(title="ignored", idempotency_key="memory-create-1"),
        owner,
    )
    assert repeated.id == draft.id
    assert await memories.list_family_memories(seed.family_id, owner) == []
    assert [
        m.id
        for m in await memories.list_family_memories(seed.family_id, owner, include_my_drafts=True)
    ] == [draft.id]
    assert (
        await memories.list_family_memories(
            seed.family_id, User(id=relative), include_my_drafts=True
        )
        == []
    )

    with pytest.raises(HTTPException) as hidden:
        await memories.get_family_memory(draft.id, User(id=relative))
    assert hidden.value.status_code == 404
    with pytest.raises(HTTPException) as cross_family:
        await memories.list_family_memories(seed.family_id, User(id=outsider))
    assert cross_family.value.status_code == 403

    changed = await memories.update_family_memory(
        draft.id,
        UpdateFamilyMemory(description="A short description", language="es"),
        owner,
    )
    assert (changed.title, changed.description, changed.language) == (
        "Childhood home",
        "A short description",
        "es",
    )
    with pytest.raises(HTTPException) as edit_denied:
        await memories.update_family_memory(
            draft.id, UpdateFamilyMemory(title="Stolen"), User(id=relative)
        )
    assert edit_denied.value.status_code == 404

    with pytest.raises(HTTPException):
        await memories.list_family_memories(seed.family_id, owner, limit=51)


async def test_upload_validation_retry_publish_and_family_read(conn, fakes, seed):
    relative, _ = await add_member(conn, seed.family_id, "Relative")
    draft = await memories.create_family_memory(
        seed.family_id,
        CreateFamilyMemory(title="Graduation", description="A proud day"),
        User(id=seed.user_id),
    )
    with pytest.raises(HTTPException) as not_ready:
        await memories.publish_family_memory(draft.id, User(id=seed.user_id))
    assert not_ready.value.status_code == 422

    pending = await memories.create_memory_upload(
        draft.id,
        CreateUpload(kind="photo", mime="image/png", byte_size=4),
        User(id=seed.user_id),
    )
    with pytest.raises(HTTPException) as interrupted:
        await memories.complete_memory_upload(draft.id, pending.media_id, User(id=seed.user_id))
    assert interrupted.value.status_code == 409
    retried = await memories.retry_memory_upload(draft.id, pending.media_id, User(id=seed.user_id))
    assert retried.media_id == pending.media_id and "/photos/" in retried.upload_url

    path = await conn.fetchval("select storage_path from media where id = $1", pending.media_id)
    fakes.files[path] = b"wrong-size"
    fakes.file_mimes[path] = "image/png"
    with pytest.raises(HTTPException) as mismatch:
        await memories.complete_memory_upload(draft.id, pending.media_id, User(id=seed.user_id))
    assert mismatch.value.status_code == 422
    assert await conn.fetchval(
        "select upload_status from media where id = $1", pending.media_id
    ) == ("failed")
    await memories.retry_memory_upload(draft.id, pending.media_id, User(id=seed.user_id))
    assert path not in fakes.files
    await memories.delete_memory_media(draft.id, pending.media_id, User(id=seed.user_id))

    _, _, _ = await upload(
        conn, fakes, draft.id, seed.user_id, "photo", "image/jpeg", b"valid-photo"
    )
    _, _, _ = await upload(
        conn, fakes, draft.id, seed.user_id, "audio", "audio/wav", b"valid-audio"
    )
    published = await memories.publish_family_memory(draft.id, User(id=seed.user_id))
    assert published.status == "published"
    assert len(published.photos) == 1 and published.recording is not None

    family_list = await memories.list_family_memories(seed.family_id, User(id=relative))
    assert [(item.id, item.title) for item in family_list] == [(draft.id, "Graduation")]
    detail = await memories.get_family_memory(draft.id, User(id=relative))
    assert detail.audio_url.startswith("https://storage.test/audio/")
    assert detail.photos[0].url.startswith("https://storage.test/photos/")


async def test_photo_selection_order_and_attachment_ownership(conn, fakes, seed):
    relative, _ = await add_member(conn, seed.family_id, "Relative")
    draft = await memories.create_family_memory(
        seed.family_id, CreateFamilyMemory(title="Album"), User(id=seed.user_id)
    )
    owned = uuid4()
    theirs = uuid4()
    await conn.executemany(
        "insert into media (id, family_id, kind, storage_path, mime, byte_size, created_by) "
        "values ($1, $2, 'photo', $3, 'image/jpeg', 5, $4)",
        [
            (owned, seed.family_id, f"{seed.family_id}/archive/{owned}.jpg", seed.user_id),
            (theirs, seed.family_id, f"{seed.family_id}/archive/{theirs}.jpg", relative),
        ],
    )
    fakes.files[f"{seed.family_id}/archive/{owned}.jpg"] = b"owned"
    fakes.file_mimes[f"{seed.family_id}/archive/{owned}.jpg"] = "image/jpeg"
    attached = await memories.attach_existing_photo(
        draft.id, AttachPhoto(media_id=owned), User(id=seed.user_id)
    )
    with pytest.raises(HTTPException) as someone_elses:
        await memories.attach_existing_photo(
            draft.id, AttachPhoto(media_id=theirs), User(id=seed.user_id)
        )
    assert someone_elses.value.status_code == 404

    uploaded, _, _ = await upload(
        conn, fakes, draft.id, seed.user_id, "photo", "image/png", b"second"
    )
    reordered = await memories.reorder_memory_photos(
        draft.id, ReorderPhotos(media_ids=[uploaded, owned]), User(id=seed.user_id)
    )
    assert [photo.id for photo in reordered.photos] == [uploaded, owned]
    assert reordered.cover_url.endswith(f"{uploaded}.png")
    assert attached.photos[0].id == owned


async def test_permissions_storage_privacy_and_delete_integrity(conn, fakes, seed, monkeypatch):
    relative, _ = await add_member(conn, seed.family_id, "Relative")
    detail, photo_id, audio_id, photo_path, audio_path = await published_memory(conn, fakes, seed)
    draft = await memories.create_family_memory(
        seed.family_id, CreateFamilyMemory(title="Private"), User(id=seed.user_id)
    )
    draft_photo, draft_path, _ = await upload(
        conn, fakes, draft.id, seed.user_id, "photo", "image/jpeg", b"private"
    )
    pending = await memories.create_memory_upload(
        detail.id,
        CreateUpload(kind="photo", mime="image/png", byte_size=7),
        User(id=seed.user_id),
    )
    pending_path = await conn.fetchval(
        "select storage_path from media where id = $1", pending.media_id
    )
    await conn.executemany(
        "insert into storage.objects (bucket_id, name) values ($1, $2)",
        [
            ("photos", draft_path),
            ("photos", photo_path),
            ("audio", audio_path),
            ("photos", pending_path),
        ],
    )

    assert await visible(conn, seed.user_id, "select count(*) from family_memory") == 2
    assert await visible(conn, relative, "select count(*) from family_memory") == 1
    assert (
        await visible(conn, relative, "select count(*) from media where memory_id = $1", draft.id)
        == 0
    )
    assert (
        await visible(
            conn,
            relative,
            "select count(*) from storage.objects where name = $1",
            draft_path,
        )
        == 0
    )
    assert (
        await visible(
            conn,
            relative,
            "select count(*) from storage.objects where name in ($1, $2)",
            photo_path,
            audio_path,
        )
        == 2
    )
    assert (
        await visible(
            conn,
            relative,
            "select count(*) from media where memory_id = $1",
            detail.id,
        )
        == 2
    )
    assert (
        await visible(
            conn,
            relative,
            "select count(*) from storage.objects where name = $1",
            pending_path,
        )
        == 0
    )
    async with conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute(
            "select set_config('request.jwt.claim.sub', $1, true)", str(seed.user_id)
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn.transaction():
                await conn.execute(
                    "insert into family_memory (family_id, contributor_id, created_by) "
                    "values ($1, $2, $3)",
                    seed.family_id,
                    seed.narrator_id,
                    seed.user_id,
                )
        await conn.execute("reset role")

    with pytest.raises(HTTPException) as edit_denied:
        await memories.update_family_memory(
            detail.id, UpdateFamilyMemory(title="No"), User(id=relative)
        )
    assert edit_denied.value.status_code == 404
    with pytest.raises(HTTPException) as required_photo:
        await memories.delete_memory_media(detail.id, photo_id, User(id=seed.user_id))
    assert required_photo.value.status_code == 409
    with pytest.raises(HTTPException) as required_audio:
        await memories.delete_memory_media(detail.id, audio_id, User(id=seed.user_id))
    assert required_audio.value.status_code == 409

    original_delete = storage.delete_objects

    async def ambiguous_delete(bucket, paths):
        await original_delete(bucket, paths)
        raise RuntimeError("storage response lost after deletion")

    monkeypatch.setattr(storage, "delete_objects", ambiguous_delete)
    with pytest.raises(RuntimeError, match="response lost"):
        await memories.delete_family_memory(draft.id, User(id=seed.user_id))
    assert await conn.fetchval("select count(*) from family_memory where id = $1", draft.id) == 1
    assert await conn.fetchval("select count(*) from media where id = $1", draft_photo) == 1
    assert draft_path not in fakes.files

    monkeypatch.setattr(storage, "delete_objects", original_delete)
    await memories.delete_family_memory(draft.id, User(id=seed.user_id))
    assert await conn.fetchval("select count(*) from family_memory where id = $1", draft.id) == 0
    assert draft_path not in fakes.files


async def test_deletion_refuses_shared_and_protected_media(conn, fakes, seed):
    first = await memories.create_family_memory(
        seed.family_id, CreateFamilyMemory(title="First"), User(id=seed.user_id)
    )
    second = await memories.create_family_memory(
        seed.family_id, CreateFamilyMemory(title="Second"), User(id=seed.user_id)
    )
    photo_id, path, _ = await upload(
        conn, fakes, first.id, seed.user_id, "photo", "image/jpeg", b"shared-photo"
    )
    await conn.execute(
        "insert into family_memory_photo (memory_id, media_id, position) values ($1, $2, 0)",
        second.id,
        photo_id,
    )

    with pytest.raises(HTTPException) as shared:
        await memories.delete_family_memory(first.id, User(id=seed.user_id))
    assert shared.value.status_code == 409
    assert path in fakes.files

    await conn.execute(
        "delete from family_memory_photo where memory_id = $1 and media_id = $2",
        second.id,
        photo_id,
    )
    await conn.execute(
        "update heirloom set cover_media_id = $2 where id = $1", seed.heirloom_id, photo_id
    )
    with pytest.raises(HTTPException) as protected:
        await memories.delete_memory_media(first.id, photo_id, User(id=seed.user_id))
    assert protected.value.status_code == 409
    assert path in fakes.files

    await conn.execute(
        "update heirloom set cover_media_id = $2 where id = $1", seed.heirloom_id, seed.photo_id
    )
    await memories.delete_memory_media(first.id, photo_id, User(id=seed.user_id))
    assert path not in fakes.files
    assert await conn.fetchval("select count(*) from media where id = $1", photo_id) == 0


async def test_published_pagination_is_stable(conn, fakes, seed):
    ids = []
    for title in ("One", "Two", "Three"):
        item, *_ = await published_memory(conn, fakes, seed, title=title)
        ids.append(item.id)
    page = await memories.list_family_memories(seed.family_id, User(id=seed.user_id), limit=2)
    next_page = await memories.list_family_memories(
        seed.family_id, User(id=seed.user_id), limit=2, offset=2
    )
    assert len(page) == 2 and len(next_page) == 1
    assert {item.id for item in [*page, *next_page]} == set(ids)
