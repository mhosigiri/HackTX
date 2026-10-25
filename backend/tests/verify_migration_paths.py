"""Isolated fresh-install and post-invitation upgrade checks for local migrations.

Run with:
  uv run --python 3.12 --with pgserver --with asyncpg python tests/verify_migration_paths.py
"""

import asyncio
import tempfile
from pathlib import Path
from uuid import uuid4

import asyncpg
import pgserver

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"
STUBS = ROOT / "backend" / "tests" / "supabase_stubs.sql"
INVITATION_VERSION = "20261025061842"
NOTIFICATION_VERSION = "20261028030000"
MIGRATION_FILES = sorted(MIGRATIONS.glob("*.sql"))
SQL = {path: path.read_text() for path in [STUBS, *MIGRATION_FILES]}


async def apply(conn: asyncpg.Connection, path: Path) -> None:
    await conn.execute(SQL[path])


async def fresh_install(uri: str) -> None:
    conn = await asyncpg.connect(uri)
    try:
        await apply(conn, STUBS)
        for path in MIGRATION_FILES:
            await apply(conn, path)
        assert await conn.fetchval("select to_regclass('public.family_memory')")
        assert await conn.fetchval("select to_regclass('public.private_schedule_entry')")
        assert await conn.fetchval("select to_regclass('public.notification')")
        check = await conn.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid = 'notification'::regclass and conname = 'notification_type_check'"
        )
        assert "storytime_ready" in check
    finally:
        await conn.close()


async def upgrade_after_invitations(uri: str) -> None:
    conn = await asyncpg.connect(uri)
    try:
        await apply(conn, STUBS)
        paths = MIGRATION_FILES
        for path in paths:
            await apply(conn, path)
            if path.name.startswith(INVITATION_VERSION):
                break

        owner, relative = uuid4(), uuid4()
        family, owner_person, relative_person = uuid4(), uuid4(), uuid4()
        await conn.executemany(
            "insert into auth.users (id, email, email_confirmed_at) values ($1, $2, now())",
            [(owner, "owner-upgrade@example.com"), (relative, "relative-upgrade@example.com")],
        )
        await conn.execute(
            "insert into family (id, name, invite_code) values ($1, 'Preserved', 'upgrade')",
            family,
        )
        await conn.executemany(
            "insert into person (id, family_id, display_name) values ($1, $2, $3)",
            [
                (owner_person, family, "Owner Person"),
                (relative_person, family, "Relative Person"),
            ],
        )
        await conn.executemany(
            "insert into member (user_id, family_id, person_id, role) values ($1, $2, $3, $4)",
            [
                (owner, family, owner_person, "owner"),
                (relative, family, relative_person, "member"),
            ],
        )
        await conn.execute(
            "insert into relationship (family_id, a, b, kind) values ($1, $2, $3, 'sibling')",
            family,
            owner_person,
            relative_person,
        )
        await conn.execute(
            "insert into profile (user_id, display_name, age, ui_mode) "
            "values ($1, 'Private profile name', 72, 'regular')",
            relative,
        )
        invite_id = await conn.fetchval(
            "insert into family_invite "
            "(family_id, inviter_user_id, anchor_person_id, kind, email, status, "
            " accepted_user_id, person_id, responded_at) "
            "values ($1, $2, $3, 'sibling', 'relative-upgrade@example.com', 'accepted', "
            "$4, $5, now()) returning id",
            family,
            owner,
            owner_person,
            relative,
            relative_person,
        )

        for path in paths:
            if path.name[:14] <= INVITATION_VERSION:
                continue
            if path.name.startswith(NOTIFICATION_VERSION):
                # The hosted protected Storytime migration is already applied and extends this
                # shared check constraint. The supporting migration must preserve that value.
                await conn.execute(
                    "alter table notification drop constraint notification_type_check; "
                    "alter table notification add constraint notification_type_check check "
                    "(type in ('request_received', 'request_declined', 'story_ready', "
                    "'memory_added', 'storytime_ready'))"
                )
            await apply(conn, path)

        assert await conn.fetchval("select count(*) from auth.users") == 2
        assert await conn.fetchval("select count(*) from family where id = $1", family) == 1
        assert await conn.fetchval("select count(*) from person where family_id = $1", family) == 2
        assert await conn.fetchval("select count(*) from member where family_id = $1", family) == 2
        assert (
            await conn.fetchval("select count(*) from relationship where family_id = $1", family)
            == 1
        )
        assert (
            await conn.fetchval("select count(*) from family_invite where id = $1", invite_id) == 1
        )
        profile = await conn.fetchrow(
            "select display_name, preferred_language, ui_mode, ui_mode_overridden "
            "from profile where user_id = $1",
            relative,
        )
        assert tuple(profile) == ("Private profile name", "en", "regular", True)
        await conn.execute(
            "insert into notification (recipient_id, type) values ($1, 'storytime_ready')",
            relative_person,
        )
        async with conn.transaction():
            await conn.execute("set local role authenticated")
            await conn.execute(
                "select set_config('request.jwt.claim.sub', $1, true)", str(relative)
            )
            assert (
                await conn.fetchval(
                    "select count(*) from notification where type = 'storytime_ready'"
                )
                == 1
            )
    finally:
        await conn.close()


def main() -> None:
    fresh = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    upgrade = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    try:
        asyncio.run(fresh_install(fresh.get_uri()))
        asyncio.run(upgrade_after_invitations(upgrade.get_uri()))
    finally:
        fresh.cleanup()
        upgrade.cleanup()
    print("fresh install: ok")
    print(f"upgrade after {INVITATION_VERSION}: ok")
    print("protected notification type preservation: ok")


if __name__ == "__main__":
    main()
