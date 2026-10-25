"""Persisted profile, language, and age-derived/manual display preferences."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.auth import CurrentUser
from app.db import pool

router = APIRouter(prefix="/api/profile", tags=["profile"])

DisplayMode = Literal["regular", "simplified", "extra_simple"]
PreferredLanguage = Literal["en", "es", "hi"]


def default_mode(age: int | None) -> str:
    if age is None:
        return "simplified"
    if age < 18:
        return "regular"
    if age <= 50:
        return "simplified"
    return "extra_simple"


class Profile(BaseModel):
    user_id: str
    display_name: str | None = None
    age: int | None = None
    ui_mode: DisplayMode = "simplified"
    ui_mode_is_manual: bool = False
    preferred_language: PreferredLanguage = "en"


class UpdateProfile(BaseModel):
    display_name: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    ui_mode: DisplayMode | None = None
    preferred_language: PreferredLanguage | None = None

    @field_validator("ui_mode", "preferred_language")
    @classmethod
    def preferences_cannot_be_cleared(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("preference cannot be null")
        return value


@router.get("")
async def get_profile(user: CurrentUser) -> Profile:
    async with pool().acquire() as conn:
        r = await conn.fetchrow(
            "select user_id::text, display_name, age, ui_mode, "
            "ui_mode_overridden as ui_mode_is_manual, preferred_language "
            "from profile where user_id = $1",
            user.id,
        )
        if r is None:
            person = await conn.fetchrow(
                "select display_name from person where id in "
                "(select person_id from member where user_id = $1 limit 1)",
                user.id,
            )
            return Profile(
                user_id=str(user.id),
                display_name=person["display_name"] if person else None,
                age=None,
                ui_mode="simplified",
                ui_mode_is_manual=False,
                preferred_language="en",
            )
    return Profile(**r)


@router.patch("")
async def update_profile(body: UpdateProfile, user: CurrentUser) -> Profile:
    async with pool().acquire() as conn:
        cur = await conn.fetchrow(
            "select age, ui_mode, ui_mode_overridden, preferred_language "
            "from profile where user_id = $1",
            user.id,
        )
        age = body.age if body.age is not None else (cur["age"] if cur else None)
        if body.ui_mode is not None:
            mode = body.ui_mode
            mode_is_manual = True
        elif body.age is not None and not (cur and cur["ui_mode_overridden"]):
            mode = default_mode(body.age)
            mode_is_manual = False
        else:
            mode = cur["ui_mode"] if cur else "simplified"
            mode_is_manual = cur["ui_mode_overridden"] if cur else False
        language = (
            body.preferred_language
            if body.preferred_language is not None
            else (cur["preferred_language"] if cur else "en")
        )
        person = await conn.fetchrow(
            "select display_name from person where id in "
            "(select person_id from member where user_id = $1 limit 1)",
            user.id,
        )
        name = (
            body.display_name
            if body.display_name is not None
            else (person["display_name"] if person else None)
        )
        r = await conn.fetchrow(
            """
            insert into profile
              (user_id, display_name, age, ui_mode, ui_mode_overridden, preferred_language)
            values ($1, $2, $3, $4, $5, $6)
            on conflict (user_id) do update set
              display_name = excluded.display_name,
              age = excluded.age,
              ui_mode = excluded.ui_mode,
              ui_mode_overridden = excluded.ui_mode_overridden,
              preferred_language = excluded.preferred_language
            returning user_id::text, display_name, age, ui_mode,
              ui_mode_overridden as ui_mode_is_manual, preferred_language
            """,
            user.id,
            name,
            age,
            mode,
            mode_is_manual,
            language,
        )
    return Profile(**r)
