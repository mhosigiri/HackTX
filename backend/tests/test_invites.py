"""Family invitations: who may invite, who may answer, and what an answer changes."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.auth import User
from app.routers import families, invites
from app.routers.families import CreateFamily
from app.routers.invites import CreateInvite, edge, normalize_email
from tests.test_brief_fixes import visible


async def add_user(conn, email: str, confirmed: bool = True) -> User:
    user_id = uuid4()
    await conn.execute(
        "insert into auth.users (id, email, email_confirmed_at) "
        "values ($1, $2, case when $3::boolean then now() end)",
        user_id,
        email,
        confirmed,
    )
    return User(id=user_id)


async def new_family(conn, owner: User, name="Maya") -> tuple[UUID, UUID]:
    family = await families.create_family(CreateFamily(name="KC", your_name=name), owner)
    tree = await families.get_tree(family.id, owner)
    return family.id, tree.me


async def invite(family_id, anchor, kind, email, user):
    return await invites.create_invite(
        family_id, CreateInvite(anchor_person_id=anchor, kind=kind, email=email), user
    )


async def status_of(call) -> int:
    with pytest.raises(HTTPException) as e:
        await call
    return e.value.status_code


async def counts(conn, family_id):
    return (
        await conn.fetchval("select count(*) from member where family_id = $1", family_id),
        await conn.fetchval("select count(*) from person where family_id = $1", family_id),
        await conn.fetchval("select count(*) from relationship where family_id = $1", family_id),
    )


def test_relationship_direction_maps_onto_edges():
    anchor, recipient = uuid4(), uuid4()
    assert edge("parent", anchor, recipient) == (recipient, anchor, "parent")
    assert edge("child", anchor, recipient) == (anchor, recipient, "parent")
    assert edge("sibling", anchor, recipient) == (recipient, anchor, "sibling")
    assert edge("spouse", anchor, recipient) == (recipient, anchor, "spouse")


def test_email_is_normalized_and_validated():
    assert normalize_email("  Grandpa@Example.COM ") == "grandpa@example.com"
    for bad in ("grandpa", "@example.com", "a@b", "a@@b.com", "a b@c.com"):
        with pytest.raises(HTTPException):
            normalize_email(bad)


async def test_accepting_a_parent_invite_joins_the_recipient_as_the_anchors_parent(conn):
    owner = await add_user(conn, "maya@example.com")
    grandpa = await add_user(conn, "grandpa@example.com")
    family_id, maya = await new_family(conn, owner)
    await conn.execute("insert into profile (user_id, display_name) values ($1, 'Raj')", grandpa.id)

    sent = await invite(family_id, maya, "parent", "Grandpa@Example.com", owner)
    assert (sent.status, sent.email, sent.anchor_name) == ("pending", "grandpa@example.com", "Maya")
    assert await counts(conn, family_id) == (1, 1, 0), "nothing changes until they accept"

    seen = await invites.get_invite(sent.id, grandpa)
    assert seen.can_respond and seen.inviter_name == "Maya"
    done = await invites.accept_invite(sent.id, grandpa)
    assert done.status == "accepted" and done.person_id

    tree = await families.get_tree(family_id, grandpa)
    assert tree.me == done.person_id
    assert [(r.a, r.b, r.kind) for r in tree.relationships] == [(done.person_id, maya, "parent")]
    assert {p.display_name for p in tree.people} == {"Maya", "Raj"}
    assert set(tree.member_person_ids) == {maya, done.person_id}


async def test_child_invite_points_the_parent_edge_from_the_anchor(conn):
    owner = await add_user(conn, "maya@example.com")
    kid = await add_user(conn, "kid@example.com")
    family_id, maya = await new_family(conn, owner)
    sent = await invite(family_id, maya, "child", "kid@example.com", owner)
    done = await invites.accept_invite(sent.id, kid)
    edges = await conn.fetch("select a, b, kind from relationship where family_id = $1", family_id)
    assert [tuple(r) for r in edges] == [(maya, done.person_id, "parent")]


async def test_only_members_create_or_list_and_only_family_or_recipient_read(conn):
    owner = await add_user(conn, "maya@example.com")
    outsider = await add_user(conn, "stranger@example.com")
    family_id, maya = await new_family(conn, owner)
    other_family, stranger = await new_family(conn, outsider, "Stranger")
    sent = await invite(family_id, maya, "sibling", "sis@example.com", owner)

    assert await status_of(invite(family_id, maya, "sibling", "x@example.com", outsider)) == 403
    assert await status_of(invites.list_invites(family_id, outsider)) == 403
    assert await status_of(invites.get_invite(sent.id, outsider)) == 403
    assert await status_of(families.get_tree(family_id, outsider)) == 403
    assert await status_of(invite(family_id, stranger, "parent", "x@example.com", owner)) == 404
    assert [i.id for i in await invites.list_invites(family_id, owner)] == [sent.id]
    assert not (await invites.get_invite(sent.id, owner)).can_respond, "inviter can't answer"
    assert await invites.list_invites(other_family, outsider) == []


async def test_invites_are_visible_through_rls_only_to_family_members(conn):
    owner = await add_user(conn, "maya@example.com")
    outsider = await add_user(conn, "stranger@example.com")
    family_id, maya = await new_family(conn, owner)
    await new_family(conn, outsider, "Stranger")
    await invite(family_id, maya, "sibling", "sis@example.com", owner)
    sql = "select count(*) from family_invite"
    assert await visible(conn, owner.id, sql) == 1
    assert await visible(conn, outsider.id, sql) == 0


async def test_answers_require_the_verified_recipient_email(conn):
    owner = await add_user(conn, "maya@example.com")
    wrong = await add_user(conn, "someone@example.com")
    unconfirmed = await add_user(conn, "sis@example.com", confirmed=False)
    family_id, maya = await new_family(conn, owner)
    sent = await invite(family_id, maya, "sibling", "sis@example.com", owner)

    assert await status_of(invites.accept_invite(sent.id, wrong)) == 403
    assert await status_of(invites.decline_invite(sent.id, wrong)) == 403
    assert await status_of(invites.accept_invite(sent.id, owner)) == 403, "inviter isn't recipient"
    assert await status_of(invites.accept_invite(sent.id, unconfirmed)) == 403
    assert await counts(conn, family_id) == (1, 1, 0)
    assert (await invites.get_invite(sent.id, owner)).status == "pending"


async def test_repeated_and_concurrent_accepts_join_once(conn):
    owner = await add_user(conn, "maya@example.com")
    sis = await add_user(conn, "sis@example.com")
    family_id, maya = await new_family(conn, owner)
    sent = await invite(family_id, maya, "sibling", "sis@example.com", owner)

    first, second = await asyncio.gather(
        invites.accept_invite(sent.id, sis), invites.accept_invite(sent.id, sis)
    )
    again = await invites.accept_invite(sent.id, sis)
    assert first.person_id == second.person_id == again.person_id
    assert await counts(conn, family_id) == (2, 2, 1)
    assert await status_of(invites.decline_invite(sent.id, sis)) == 409


async def test_declined_invites_cannot_be_accepted(conn):
    owner = await add_user(conn, "maya@example.com")
    sis = await add_user(conn, "sis@example.com")
    family_id, maya = await new_family(conn, owner)
    sent = await invite(family_id, maya, "sibling", "sis@example.com", owner)

    assert (await invites.decline_invite(sent.id, sis)).status == "declined"
    assert (await invites.decline_invite(sent.id, sis)).status == "declined", "idempotent"
    assert await status_of(invites.accept_invite(sent.id, sis)) == 409
    assert await counts(conn, family_id) == (1, 1, 0)
    resent = await invite(family_id, maya, "sibling", "sis@example.com", owner)
    assert resent.status == "pending", "a declined invitation doesn't block a new one"


async def test_invalid_invitations_are_rejected(conn):
    owner = await add_user(conn, "maya@example.com")
    family_id, maya = await new_family(conn, owner)
    assert await status_of(invite(family_id, maya, "parent", "MAYA@example.com", owner)) == 400
    assert await status_of(invite(family_id, uuid4(), "parent", "a@example.com", owner)) == 404
    assert await status_of(invite(family_id, maya, "parent", "not-an-email", owner)) == 422
    await invite(family_id, maya, "parent", "dad@example.com", owner)
    assert await status_of(invite(family_id, maya, "child", "dad@example.com", owner)) == 409


async def test_a_failed_accept_rolls_back_membership_and_person(conn):
    owner = await add_user(conn, "maya@example.com")
    third = await add_user(conn, "third@example.com")
    family_id, maya = await new_family(conn, owner)
    sent = await invite(family_id, maya, "parent", "third@example.com", owner)
    for name in ("Mum", "Dad"):
        parent = await conn.fetchval(
            "insert into person (family_id, display_name) values ($1, $2) returning id",
            family_id,
            name,
        )
        await conn.execute(
            "insert into relationship values ($1, $2, $3, 'parent')", family_id, parent, maya
        )
    before = await counts(conn, family_id)

    assert await status_of(invites.accept_invite(sent.id, third)) == 409
    assert await counts(conn, family_id) == before, "no member, person, or edge left behind"
    assert await conn.fetchval("select count(*) from member where user_id = $1", third.id) == 0
    assert (await invites.get_invite(sent.id, owner)).status == "pending"


async def test_existing_members_reuse_their_person_and_tree_rules_hold(conn):
    owner = await add_user(conn, "maya@example.com")
    dad = await add_user(conn, "dad@example.com")
    family_id, maya = await new_family(conn, owner)
    first = await invites.accept_invite(
        (await invite(family_id, maya, "parent", "dad@example.com", owner)).id, dad
    )

    # Already connected: refused when sending, since we know who the email belongs to.
    assert await status_of(invite(family_id, maya, "child", "dad@example.com", owner)) == 409
    # Dad can't be invited as his own relative.
    own = invite(family_id, first.person_id, "spouse", "dad@example.com", owner)
    assert await status_of(own) == 400
    # Dad can't become the child of his own grandchild.
    grandkid = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, 'Kid') returning id", family_id
    )
    await conn.execute(
        "insert into relationship values ($1, $2, $3, 'parent')", family_id, maya, grandkid
    )
    assert await status_of(invite(family_id, grandkid, "child", "dad@example.com", owner)) == 409

    sibling = await conn.fetchval(
        "insert into person (family_id, display_name) values ($1, 'Aunt') returning id", family_id
    )
    again = await invites.accept_invite(
        (await invite(family_id, sibling, "sibling", "dad@example.com", owner)).id, dad
    )
    assert again.person_id == first.person_id, "same account, same person"
    assert (
        await conn.fetchval(
            "select count(*) from member where user_id = $1 and family_id = $2", dad.id, family_id
        )
        == 1
    )
