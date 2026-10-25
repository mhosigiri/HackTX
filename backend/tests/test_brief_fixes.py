"""Requests end in a story, video captures work, matching is real, private rows stay private."""

from uuid import UUID, uuid4

import pydantic
import pytest
from fastapi import HTTPException

from app.auth import User
from app.jobs.stages import compose_story
from app.models import Paragraph, Quote, Sentence, StoryDraft
from app.routers import heirlooms, interviews
from app.routers.heirlooms import AddMedia, CreateHeirloom, MatchPick, MatchPicks
from app.routers.interviews import CreateInterview
from tests.test_live_pipeline import add_answer, start_interview


async def add_person(conn, family_id, name, user_id=None):
    person_id = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, $2) returning id",
        family_id,
        name,
    )
    if user_id:
        await conn.execute("insert into auth.users values ($1)", user_id)
        await conn.execute(
            "insert into member values ($1, $2, $3, 'member')", user_id, family_id, person_id
        )
    return person_id


async def new_request(conn, seed, storyteller_id):
    return await conn.fetchval(
        "insert into story_request (heirloom_id, listener_id, storyteller_id, message) "
        "values ($1, $2, $3, 'Who gave you this?') returning id",
        seed.heirloom_id,
        seed.narrator_id,
        storyteller_id,
    )


# Privacy ------------------------------------------------------------------------------------


async def visible(conn, user_id: UUID, sql: str) -> int:
    async with conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", str(user_id))
        n = await conn.fetchval(sql)
        await conn.execute("reset role")
    return n


async def test_profile_preferences_are_visible_to_self_only(conn, seed):
    relative, outsider = uuid4(), uuid4()
    await add_person(conn, seed.family_id, "Raj", relative)
    other_family = await conn.fetchval(
        "insert into family (name, invite_code) values ('Other', 'zzz') returning id"
    )
    await add_person(conn, other_family, "Stranger", outsider)
    await conn.execute("insert into profile (user_id, age) values ($1, 84)", seed.user_id)

    mine = "select count(*) from profile where age = 84"
    assert await visible(conn, seed.user_id, mine) == 1
    assert await visible(conn, relative, mine) == 0, "family sees names through person, not prefs"
    assert await visible(conn, outsider, mine) == 0


async def test_notifications_are_visible_only_to_their_recipient(conn, seed):
    relative = uuid4()
    raj = await add_person(conn, seed.family_id, "Raj", relative)
    request_id = await conn.fetchval(
        "insert into story_request (heirloom_id, listener_id, storyteller_id) "
        "values ($1, $2, $3) returning id",
        seed.heirloom_id,
        seed.narrator_id,
        raj,
    )
    await conn.execute(
        "insert into notification (recipient_id, type, request_id) "
        "values ($1, 'request_received', $2)",
        raj,
        request_id,
    )

    inbox = "select count(*) from notification"
    assert await visible(conn, relative, inbox) == 1
    assert await visible(conn, seed.user_id, inbox) == 0, "same family, still not yours"


# Requests -----------------------------------------------------------------------------------


async def test_an_interview_can_answer_only_its_own_open_request(conn, fakes, seed):
    teller = await add_person(conn, seed.family_id, "Raj")
    request_id = await new_request(conn, seed, teller)
    user = User(id=seed.user_id)

    with pytest.raises(HTTPException) as wrong_narrator:
        await interviews.start_interview(
            CreateInterview(
                heirloom_id=seed.heirloom_id, narrator_id=seed.narrator_id, request_id=request_id
            ),
            user,
        )
    assert wrong_narrator.value.status_code == 400

    started = await interviews.start_interview(
        CreateInterview(heirloom_id=seed.heirloom_id, narrator_id=teller, request_id=request_id),
        user,
    )

    assert (
        await conn.fetchval("select request_id from interview where id = $1", started.interview.id)
        == request_id
    )
    assert (
        await conn.fetchval("select status from story_request where id = $1", request_id)
        == "in_progress"
    )


async def test_the_finished_story_completes_the_request_and_tells_the_listener(conn, fakes, seed):
    teller = await add_person(conn, seed.family_id, "Raj")
    request_id = await new_request(conn, seed, teller)
    interview_id = await start_interview(conn, seed, state="wrapping_up")
    await conn.execute(
        "update interview set request_id = $2, narrator_id = $3 where id = $1",
        interview_id,
        request_id,
        teller,
    )
    turn_id, _ = await add_answer(conn, fakes, seed, interview_id, idx=1)
    seg = await conn.fetchval(
        "insert into segment (turn_id, start_ms, end_ms, text) "
        "values ($1, 0, 2000, 'My mother gave it to me.') returning id",
        turn_id,
    )
    fakes.llm.responses[StoryDraft] = StoryDraft(
        title="Raj's watch",
        dek="d",
        blocks=[
            Paragraph(
                type="paragraph",
                sentences=[
                    Sentence(
                        text="His mother gave it to him.",
                        cites=[{"kind": "segment", "segment_id": seg}],
                    )
                ],
            ),
            Quote(type="quote", segment_id=seg, speaker_id=teller),
        ],
    )

    await compose_story.run(seed.heirloom_id)
    await compose_story.run(seed.heirloom_id)  # a later version must not notify again

    assert await conn.fetchval("select status from story_request where id = $1", request_id) == (
        "completed"
    )
    first = await conn.fetchrow(
        "select id, request_id, storyteller_id from story where heirloom_id = $1 and version = 1",
        seed.heirloom_id,
    )
    assert (first["request_id"], first["storyteller_id"]) == (request_id, teller)
    notes = await conn.fetch("select recipient_id, type, story_id from notification")
    assert [tuple(n) for n in notes] == [(seed.narrator_id, "story_ready", first["id"])]


# Video --------------------------------------------------------------------------------------


def test_the_cover_the_ai_reads_must_be_an_image():
    with pytest.raises(pydantic.ValidationError):
        CreateHeirloom(family_id=uuid4(), photo_mime="video/webm")


async def test_a_video_capture_is_kept_beside_the_cover(conn, fakes, seed, monkeypatch):
    async def signed_upload_url(bucket, path):
        return f"https://upload.test/{bucket}/{path}"

    monkeypatch.setattr(heirlooms, "signed_upload_url", signed_upload_url)

    added = await heirlooms.add_media(
        seed.heirloom_id, AddMedia(mime="video/webm"), User(id=seed.user_id)
    )

    row = await conn.fetchrow("select kind, storage_path from media where id = $1", added.media_id)
    assert row["kind"] == "video" and row["storage_path"].endswith(".webm")
    cover = await conn.fetchval(
        "select cover_media_id from heirloom where id = $1", seed.heirloom_id
    )
    assert cover == seed.photo_id, "the AI still reads the still photo"


# Matching -----------------------------------------------------------------------------------


async def saved_object(conn, seed, title):
    heirloom_id = await conn.fetchval(
        "insert into heirloom (family_id, title, category, created_by) "
        "values ($1, $2, 'watch', $3) returning id",
        seed.family_id,
        title,
        seed.user_id,
    )
    return heirloom_id


async def read(conn, seed):
    await conn.execute(
        "update heirloom set title = 'Gold pocket watch', category = 'watch' where id = $1",
        seed.heirloom_id,
    )
    await conn.execute(
        "insert into job (kind, subject_id, family_id, status) "
        "values ('analyze_object', $1, $2, 'done')",
        seed.heirloom_id,
        seed.family_id,
    )


async def test_matching_waits_for_the_photo_to_be_read(conn, fakes, seed):
    result = await heirlooms.find_matches(seed.heirloom_id, User(id=seed.user_id))
    assert result.status == "analyzing"


async def test_matching_returns_only_confident_matches_with_their_state(conn, fakes, seed):
    await read(conn, seed)
    same = await saved_object(conn, seed, "Grandpa's pocket watch")
    await saved_object(conn, seed, "Silver wristwatch")
    await conn.execute(
        "insert into story (heirloom_id, version, title, blocks) values ($1, 1, 't', '[]')", same
    )
    fakes.llm.responses[MatchPicks] = MatchPicks(
        matches=[
            MatchPick(index=0, confidence=0.3),  # newest first: the wristwatch
            MatchPick(index=1, confidence=0.9),
            MatchPick(index=9, confidence=0.99),
        ]
    )

    result = await heirlooms.find_matches(seed.heirloom_id, User(id=seed.user_id))

    assert [(c.heirloom.id, c.has_story) for c in result.candidates] == [(same, True)]
    assert fakes.llm.calls[-1]["effort"] == "minimal"


async def test_no_saved_objects_means_no_match_and_no_model_call(conn, fakes, seed):
    await read(conn, seed)
    result = await heirlooms.find_matches(seed.heirloom_id, User(id=seed.user_id))
    assert (result.status, result.candidates, fakes.llm.calls) == ("ready", [], [])


async def test_same_as_moves_the_capture_and_drops_the_duplicate(conn, fakes, seed):
    target = await saved_object(conn, seed, "Grandpa's pocket watch")

    merged = await heirlooms.merge_into(seed.heirloom_id, target, User(id=seed.user_id))

    assert merged.id == target
    assert (
        await conn.fetchval("select heirloom_id from media where id = $1", seed.photo_id) == target
    )
    assert await conn.fetchval("select count(*) from heirloom where id = $1", seed.heirloom_id) == 0
