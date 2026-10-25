"""Supabase Storage via its REST API. Object paths start with the family id so storage RLS can
check membership: `{family_id}/{heirloom_id}/{media_id}.{ext}`."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import httpx

from app.config import get_settings

Bucket = Literal["photos", "audio", "generated"]


@dataclass(frozen=True)
class StoredObject:
    byte_size: int
    mime: str


_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
    "video/webm": "webm",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
}


def object_path(family_id: UUID, heirloom_id: UUID, media_id: UUID, mime: str) -> str:
    return f"{family_id}/{heirloom_id}/{media_id}.{_EXT.get(mime.split(';')[0], 'bin')}"


def _headers() -> dict[str, str]:
    # New sb_secret_ keys aren't JWTs: they go on `apikey` only, never `Authorization: Bearer`.
    return {"apikey": get_settings().supabase_secret_key}


async def signed_upload_url(bucket: Bucket, path: str) -> str:
    """The browser PUTs the file body to this URL."""
    base = f"{get_settings().supabase_url}/storage/v1"
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(f"{base}/object/upload/sign/{bucket}/{path}", headers=_headers())
    return base + r.raise_for_status().json()["url"]


async def signed_download_url(bucket: Bucket, path: str, expires_in: int = 3600) -> str:
    base = f"{get_settings().supabase_url}/storage/v1"
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.post(
            f"{base}/object/sign/{bucket}/{path}",
            headers=_headers(),
            json={"expiresIn": expires_in},
        )
    return base + r.raise_for_status().json()["signedURL"]


async def object_info(bucket: Bucket, path: str) -> StoredObject | None:
    """Read the uploaded object's actual size/type before application metadata is finalized."""
    base = f"{get_settings().supabase_url}/storage/v1"
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.head(f"{base}/object/{bucket}/{path}", headers=_headers())
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return StoredObject(
        byte_size=int(r.headers["content-length"]),
        mime=r.headers["content-type"].split(";", 1)[0].lower(),
    )


async def delete_objects(bucket: Bucket, paths: list[str]) -> None:
    """Delete through Storage API; deleting storage.objects rows directly can orphan bytes."""
    base = f"{get_settings().supabase_url}/storage/v1"
    remaining = paths
    for _ in range(2):
        remaining = [path for path in remaining if await object_info(bucket, path) is not None]
        if not remaining:
            return
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.request(
                "DELETE",
                f"{base}/object/{bucket}",
                headers=_headers(),
                json={"prefixes": remaining},
            )
        if response.status_code != 404:
            response.raise_for_status()
            return
    if all(await object_info(bucket, path) is None for path in remaining):
        return
    response.raise_for_status()


async def download(bucket: Bucket, path: str) -> bytes:
    base = f"{get_settings().supabase_url}/storage/v1"
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(f"{base}/object/{bucket}/{path}", headers=_headers())
    return r.raise_for_status().content


async def upload(bucket: Bucket, path: str, data: bytes, mime: str) -> None:
    base = f"{get_settings().supabase_url}/storage/v1"
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            f"{base}/object/{bucket}/{path}",
            headers={**_headers(), "Content-Type": mime, "x-upsert": "true"},
            content=data,
        )
    r.raise_for_status()
