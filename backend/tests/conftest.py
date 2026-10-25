import io
import os
import wave
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from app import db, providers, storage
from app.providers import Providers
from app.providers.base import Blob, LensMatch, SerpResult, StreamedTranscript, Transcript

if not os.environ.get("TEST_DATABASE_URL"):
    pytest.skip("run via tests/run_with_db.sh (needs TEST_DATABASE_URL)", allow_module_level=True)


@dataclass
class FakeLLM:
    """Returns the queued response for whichever schema a stage asks for. A list is served in
    order, one item per call."""

    responses: dict[type, Any] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)

    async def json(self, *, system, messages, schema, images=None, effort=None):
        self.calls.append(
            {"system": system, "messages": list(messages), "images": images, "effort": effort}
        )
        response = self.responses[schema]
        return response.pop(0) if isinstance(response, list) else response


@dataclass
class FakeASR:
    transcript: Transcript | None = None
    calls: list[Blob] = field(default_factory=list)
    keywords: list[str] | None = None

    async def transcribe(self, *, audio, language=None, keywords=None):
        self.calls.append(audio)
        self.keywords = keywords
        return self.transcript


@dataclass
class FakeSearch:
    matches: list[LensMatch] = field(default_factory=list)
    results: list[SerpResult] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    async def lens(self, image_url):
        return self.matches

    async def web(self, q, engine="google"):
        self.queries.append(q)
        return self.results


@dataclass
class FakeStreamingASR:
    """Echoes a partial per audio chunk, then returns `result` (or raises `fail`)."""

    result: StreamedTranscript | None = None
    fail: Exception | None = None
    chunks: list[bytes] = field(default_factory=list)
    keywords: list[str] | None = None

    async def stream(self, audio, *, language=None, keywords=None, on_partial=None):
        self.keywords = keywords
        async for chunk in audio:
            self.chunks.append(chunk)
            if on_partial:
                await on_partial(f"heard {len(self.chunks)}")
        if self.fail:
            raise self.fail
        return self.result


PNG = b"\x89PNG\r\n\x1a\nfake-cover"


@dataclass
class FakeImage:
    prompts: list[str] = field(default_factory=list)

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return PNG


@dataclass
class Fakes:
    llm: FakeLLM
    asr: FakeASR
    asr_stream: FakeStreamingASR
    search: FakeSearch
    image: FakeImage
    files: dict[str, bytes]
    file_mimes: dict[str, str]


@pytest.fixture
async def fakes(monkeypatch) -> Fakes:
    f = Fakes(
        llm=FakeLLM(),
        asr=FakeASR(),
        asr_stream=FakeStreamingASR(),
        search=FakeSearch(),
        image=FakeImage(),
        files={},
        file_mimes={},
    )
    monkeypatch.setattr(
        providers,
        "get_providers",
        lambda: Providers(
            llm=f.llm,
            vision=f.llm,
            asr=f.asr,
            asr_stream=f.asr_stream,
            image=f.image,
            search=f.search,
        ),
    )

    async def download(bucket, path):
        return f.files[path]

    async def signed_download_url(bucket, path, expires_in=3600):
        return f"https://storage.test/{bucket}/{path}"

    async def signed_upload_url(bucket, path):
        return f"https://upload.test/{bucket}/{path}"

    async def object_info(bucket, path):
        data = f.files.get(path)
        if data is None:
            return None
        return storage.StoredObject(byte_size=len(data), mime=f.file_mimes[path])

    async def delete_objects(bucket, paths):
        for path in paths:
            f.files.pop(path, None)
            f.file_mimes.pop(path, None)

    async def upload(bucket, path, data, mime):
        f.files[path] = data
        f.file_mimes[path] = mime

    monkeypatch.setattr(storage, "download", download)
    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(storage, "signed_download_url", signed_download_url)
    monkeypatch.setattr(storage, "signed_upload_url", signed_upload_url)
    monkeypatch.setattr(storage, "object_info", object_info)
    monkeypatch.setattr(storage, "delete_objects", delete_objects)
    return f


@pytest.fixture
async def conn():
    await db.open_pool(os.environ["TEST_DATABASE_URL"])
    async with db.pool().acquire() as c:
        await c.execute("truncate family, auth.users, serp_cache cascade")
        yield c
    await db.close_pool()


@dataclass
class Seed:
    user_id: UUID
    family_id: UUID
    narrator_id: UUID
    heirloom_id: UUID
    photo_id: UUID


@pytest.fixture
async def seed(conn, fakes) -> Seed:
    s = Seed(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    await conn.execute("insert into auth.users values ($1)", s.user_id)
    await conn.execute(
        "insert into family (id, name, invite_code) values ($1, 'KC', 'abc')", s.family_id
    )
    await conn.execute(
        "insert into person (id, family_id, display_name, relation_label) "
        "values ($1, $2, 'Nani', 'grandmother')",
        s.narrator_id,
        s.family_id,
    )
    await conn.execute(
        "insert into member values ($1, $2, $3, 'owner')", s.user_id, s.family_id, s.narrator_id
    )
    await conn.execute(
        "insert into heirloom (id, family_id, created_by) values ($1, $2, $3)",
        s.heirloom_id,
        s.family_id,
        s.user_id,
    )
    path = f"{s.family_id}/{s.heirloom_id}/{s.photo_id}.jpg"
    await conn.execute(
        "insert into media (id, family_id, heirloom_id, kind, storage_path, mime) "
        "values ($1, $2, $3, 'photo', $4, 'image/jpeg')",
        s.photo_id,
        s.family_id,
        s.heirloom_id,
        path,
    )
    await conn.execute(
        "update heirloom set cover_media_id = $2 where id = $1", s.heirloom_id, s.photo_id
    )
    fakes.files[path] = b"\xff\xd8fake-jpeg"
    return s


def make_wav(seconds: float, rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()
