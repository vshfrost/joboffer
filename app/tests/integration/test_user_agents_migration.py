"""Міграція 0029: `user_agents` заповнюється з уже живих грантів, мертві пропускаються."""

from anyio.from_thread import BlockingPortal
from sqlalchemy import text

from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import upgrade

USER = "00000000-0000-0000-0000-0000000000a1"
OTHER_USER = "00000000-0000-0000-0000-0000000000a2"
CLAUDE = "00000000-0000-0000-0000-00000000c001"
CURSOR = "00000000-0000-0000-0000-00000000c002"
REVOKED = "00000000-0000-0000-0000-00000000c003"
EXPIRED = "00000000-0000-0000-0000-00000000c004"
CONSUMED = "00000000-0000-0000-0000-00000000c005"
CODE_ONLY = "00000000-0000-0000-0000-00000000c006"
CLAUDE_URI = "https://claude.ai/api/mcp/auth_callback"
LOCAL_URI = "http://localhost:5000/cb"


def grant_id(n: int) -> str:
    return f"00000000-0000-0000-0000-00000000f{n:03d}"


def test_live_grants_become_agents_and_dead_ones_are_skipped(
    portal: BlockingPortal, scratch_url: str
) -> None:
    clients = [
        (CLAUDE, "Claude", CLAUDE_URI),
        (CURSOR, "Cursor", LOCAL_URI),
        (REVOKED, "Revoked app", LOCAL_URI),
        (EXPIRED, "Expired app", LOCAL_URI),
        (CONSUMED, "Consumed app", LOCAL_URI),
        (CODE_ONLY, "Never exchanged", LOCAL_URI),
    ]
    # (id, користувач, клієнт, створено, відкликано)
    grants = [
        (grant_id(1), USER, CLAUDE, "2026-01-01", None),
        (grant_id(2), USER, CURSOR, "2026-01-01", None),
        (grant_id(3), USER, CURSOR, "2026-02-01", None),
        (grant_id(4), USER, REVOKED, "2026-01-01", "2026-01-02"),
        (grant_id(5), USER, EXPIRED, "2026-01-01", None),
        (grant_id(6), USER, CONSUMED, "2026-01-01", None),
        (grant_id(7), USER, CODE_ONLY, "2026-01-01", None),
        (grant_id(8), OTHER_USER, CLAUDE, "2026-01-01", None),
    ]
    # (грант, kind, чи прострочений, чи використаний)
    tokens = [
        (1, "refresh", False, False),
        (2, "refresh", False, False),
        (3, "refresh", False, False),
        (4, "refresh", False, False),
        (5, "refresh", True, False),
        (6, "refresh", False, True),
        (7, "code", False, False),
        (8, "refresh", False, False),
    ]

    async def run() -> list[tuple[str, str, str, str, str]]:
        scratch = create_engine(scratch_url)
        try:
            await upgrade(scratch, "0028")
            async with scratch.begin() as conn:
                for user, email in (
                    (USER, "a@example.com"),
                    (OTHER_USER, "b@example.com"),
                ):
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, email, display_name, "
                            "password_hash, version, created_at) "
                            "VALUES (:id, :email, 'U', 'x', 1, now())"
                        ),
                        {"id": user, "email": email},
                    )
                for client, name, uri in clients:
                    await conn.execute(
                        text(
                            "INSERT INTO oauth_clients (id, name, redirect_uris, "
                            "registration) VALUES (:id, :name, "
                            "jsonb_build_array(CAST(:uri AS text)), '{}')"
                        ),
                        {"id": client, "name": name, "uri": uri},
                    )
                for gid, user, client, created, revoked in grants:
                    await conn.execute(
                        text(
                            "INSERT INTO oauth_grants (id, user_id, client_id, "
                            "resource, created_at, revoked_at) VALUES (:id, :user, "
                            ":client, 'r', CAST(:created AS timestamptz), "
                            "CAST(:revoked AS timestamptz))"
                        ),
                        {
                            "id": gid,
                            "user": user,
                            "client": client,
                            "created": created,
                            "revoked": revoked,
                        },
                    )
                for n, kind, expired, consumed in tokens:
                    await conn.execute(
                        text(
                            "INSERT INTO oauth_tokens (digest, grant_id, kind, "
                            "expires_at, consumed_at) VALUES (:digest, :grant, "
                            ":kind, now() + CAST(:delta AS interval), "
                            "CASE WHEN :consumed THEN now() END)"
                        ),
                        {
                            "digest": f"{n:064d}",
                            "grant": grant_id(n),
                            "kind": kind,
                            "delta": "-1 hour" if expired else "30 days",
                            "consumed": consumed,
                        },
                    )
            await upgrade(scratch)
            async with scratch.connect() as conn:
                found = await conn.execute(
                    text(
                        "SELECT user_id::text, client_id::text, kind, name, "
                        "grant_id::text FROM user_agents ORDER BY user_id, client_id"
                    )
                )
                return [(r[0], r[1], r[2], r[3], r[4]) for r in found]
        finally:
            await scratch.dispose()

    assert portal.call(run) == [
        (USER, CLAUDE, "claude", "Claude", grant_id(1)),
        # Два живі гранти одного клієнта — один агент, привʼязаний до новішого.
        (USER, CURSOR, "other", "Cursor", grant_id(3)),
        (OTHER_USER, CLAUDE, "claude", "Claude", grant_id(8)),
    ]
