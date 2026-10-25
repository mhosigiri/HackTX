import secrets
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import CurrentUser, require_member
from app.db import pool

router = APIRouter(prefix="/api", tags=["families"])


class Family(BaseModel):
    id: UUID
    name: str
    invite_code: str


class Person(BaseModel):
    id: UUID
    family_id: UUID
    display_name: str
    relation_label: str | None = None
    birth_year: int | None = None
    is_living: bool = True


class Relationship(BaseModel):
    """Directed edge: `a` is the `kind` of `b` (a parent of b, a spouse of b, a sibling of b)."""

    a: UUID
    b: UUID
    kind: str


class FamilyTree(BaseModel):
    people: list[Person]
    relationships: list[Relationship]
    me: UUID | None = None
    # People with a Tell Me More account, as opposed to relatives only added by name.
    member_person_ids: list[UUID]


class CreateFamily(BaseModel):
    name: str
    your_name: str


class JoinFamily(BaseModel):
    invite_code: str
    your_name: str


class CreatePerson(BaseModel):
    family_id: UUID
    display_name: str
    relation_label: str | None = None
    birth_year: int | None = None
    is_living: bool = True


@router.get("/families")
async def list_families(user: CurrentUser) -> list[Family]:
    rows = await pool().fetch(
        "select f.id, f.name, f.invite_code from family f "
        "join member m on m.family_id = f.id where m.user_id = $1 order by f.created_at",
        user.id,
    )
    return [Family(**r) for r in rows]


@router.post("/families", status_code=status.HTTP_201_CREATED)
async def create_family(body: CreateFamily, user: CurrentUser) -> Family:
    async with pool().acquire() as conn, conn.transaction():
        family = await conn.fetchrow(
            "insert into family (name, invite_code) values ($1, $2) "
            "returning id, name, invite_code",
            body.name,
            secrets.token_urlsafe(6),
        )
        person_id = await conn.fetchval(
            "insert into person (family_id, display_name) values ($1, $2) returning id",
            family["id"],
            body.your_name,
        )
        await conn.execute(
            "insert into member (user_id, family_id, person_id, role) values ($1, $2, $3, 'owner')",
            user.id,
            family["id"],
            person_id,
        )
    return Family(**family)


@router.post("/families/join")
async def join_family(body: JoinFamily, user: CurrentUser) -> Family:
    async with pool().acquire() as conn, conn.transaction():
        family = await conn.fetchrow(
            "select id, name, invite_code from family where invite_code = $1", body.invite_code
        )
        if family is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invite code not found")
        already = await conn.fetchval(
            "select 1 from member where user_id = $1 and family_id = $2", user.id, family["id"]
        )
        if not already:
            person_id = await conn.fetchval(
                "insert into person (family_id, display_name) values ($1, $2) returning id",
                family["id"],
                body.your_name,
            )
            await conn.execute(
                "insert into member (user_id, family_id, person_id) values ($1, $2, $3)",
                user.id,
                family["id"],
                person_id,
            )
    return Family(**family)


@router.get("/families/{family_id}/people")
async def list_people(family_id: UUID, user: CurrentUser) -> list[Person]:
    async with pool().acquire() as conn:
        await require_member(conn, user, family_id)
        rows = await conn.fetch(
            "select id, family_id, display_name, relation_label, birth_year, is_living "
            "from person where family_id = $1 order by created_at",
            family_id,
        )
    return [Person(**r) for r in rows]


@router.get("/families/{family_id}/tree")
async def get_tree(family_id: UUID, user: CurrentUser) -> FamilyTree:
    async with pool().acquire() as conn:
        me = await require_member(conn, user, family_id)
        people = await conn.fetch(
            "select id, family_id, display_name, relation_label, birth_year, is_living "
            "from person where family_id = $1 order by created_at",
            family_id,
        )
        edges = await conn.fetch(
            "select a, b, kind from relationship where family_id = $1", family_id
        )
        members = await conn.fetch(
            "select person_id from member where family_id = $1 and person_id is not null",
            family_id,
        )
    return FamilyTree(
        people=[Person(**r) for r in people],
        relationships=[Relationship(**r) for r in edges],
        me=me,
        member_person_ids=[r["person_id"] for r in members],
    )


@router.post("/people", status_code=status.HTTP_201_CREATED)
async def create_person(body: CreatePerson, user: CurrentUser) -> Person:
    async with pool().acquire() as conn:
        await require_member(conn, user, body.family_id)
        row = await conn.fetchrow(
            "insert into person (family_id, display_name, relation_label, birth_year, is_living) "
            "values ($1, $2, $3, $4, $5) "
            "returning id, family_id, display_name, relation_label, birth_year, is_living",
            body.family_id,
            body.display_name,
            body.relation_label,
            body.birth_year,
            body.is_living,
        )
    return Person(**row)
