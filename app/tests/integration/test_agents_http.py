"""Агенти користувача через HTTP наскрізь: сесія, справжній OAuth-флоу (authorize → код → токени) і Postgres.

Агент «підключений», поки живий його грант: не відкликаний, з невикористаним і непрострочаним refresh-токеном.
"""

from uuid import UUID, uuid4

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.oauth import AuthorizationRequest, TokenPair
from bootstrap.api import container_of
from domain.identity.ids import GrantId, UserId
from domain.oauth.entities import OAuthClient
from domain.oauth.ids import ClientId
from infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from tests.integration.test_profile_http import (
    ClientFactory,
    Session,
    make_client,
)

__all__ = ["make_client"]

CLAUDE_AI = "https://claude.ai/api/mcp/auth_callback"
CLAUDE_CODE = "http://localhost:54545/callback"
CHATGPT = "https://chatgpt.com/connector_platform_oauth_redirect"
CODEX = "http://127.0.0.1:1455/auth/callback"


class Agents:
    def __init__(
        self,
        session: Session,
        portal: BlockingPortal,
        engine: AsyncEngine,
        email: str,
    ) -> None:
        self.client = session.client
        self._portal = portal
        self._engine = engine
        self._email = email
        self._oauth = container_of(self.client.app).oauth  # type: ignore[arg-type]
        self._tokens: dict[GrantId, TokenPair] = {}

    def get(self) -> httpx2.Response:
        return self.client.get("/agents")

    def listed(self) -> list[dict[str, str]]:
        """Що бачить користувач: вид і назва (id перевіряється окремо)."""
        response = self.get()
        assert response.status_code == 200, response.text
        return [{"kind": a["kind"], "name": a["name"]} for a in response.json()]

    def user(self) -> UserId:
        async def run() -> UserId:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                return UserId(row.scalar_one())

        return self._portal.call(run)

    def register(self, name: str | None, redirect_uri: str) -> ClientId:
        """DCR-клієнт напряму в базі: allowlist перевіряє SDK на /register, тут він не потрібен."""
        client = OAuthClient(
            id=ClientId(uuid4()),
            name=name,
            redirect_uris=(redirect_uri,),
            metadata={},
        )
        factory = container_of(self.client.app).unit_of_work  # type: ignore[arg-type]

        async def run() -> None:
            async with factory() as tx:
                assert isinstance(tx, SqlAlchemyUnitOfWork)
                await tx.oauth_clients.add(client)
                await tx.commit()

        self._portal.call(run)
        return client.id

    def authorize(self, client: ClientId, redirect_uri: str) -> tuple[GrantId, str]:
        """Користувач увійшов у логін-гейті: грант і код (токенів ще нема)."""
        rid = self._portal.call(
            self._oauth.begin_authorization,
            AuthorizationRequest(
                client_id=str(client),
                redirect_uri=redirect_uri,
                redirect_uri_provided_explicitly=True,
                state=None,
                code_challenge="c" * 43,
                resource=None,
            ),
        )
        granted = self._portal.call(
            self._oauth.complete_authorization, rid, self.user()
        )
        return granted.grant_id, granted.code

    def connect(self, client: ClientId, redirect_uri: str) -> GrantId:
        """Повний флоу: грант, код, обмін на токени."""
        grant, code = self.authorize(client, redirect_uri)
        self._tokens[grant] = self._portal.call(
            self._oauth.exchange_code, str(client), code
        )
        return grant

    def connect_new(self, name: str | None, redirect_uri: str) -> GrantId:
        return self.connect(self.register(name, redirect_uri), redirect_uri)

    def revoke(self, grant: GrantId) -> None:
        self._portal.call(self._oauth.revoke, self._tokens[grant].access_token)

    def update_refresh(self, grant: GrantId, change: TextClause) -> None:
        async def run() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(change, {"grant": grant.value})

        self._portal.call(run)

    def expire_refresh(self, grant: GrantId) -> None:
        self.update_refresh(
            grant,
            text(
                "UPDATE oauth_tokens SET expires_at = now() - interval '1 hour' "
                "WHERE grant_id = :grant AND kind = 'refresh'"
            ),
        )

    def consume_refresh(self, grant: GrantId) -> None:
        self.update_refresh(
            grant,
            text(
                "UPDATE oauth_tokens SET consumed_at = now() "
                "WHERE grant_id = :grant AND kind = 'refresh'"
            ),
        )

    def stored_agents(self) -> list[tuple[UUID, UUID | None]]:
        """(id агента, його грант) із таблиці user_agents."""

        user = self.user()

        async def run() -> list[tuple[UUID, UUID | None]]:
            async with self._engine.connect() as conn:
                rows = await conn.execute(
                    text("SELECT id, grant_id FROM user_agents WHERE user_id = :u"),
                    {"u": user.value},
                )
                return [(row[0], row[1]) for row in rows]

        return self._portal.call(run)


@pytest.fixture
def alice(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> Agents:
    email = "alice@example.com"
    return Agents(Session(make_client(), email), portal, engine, email)


@pytest.fixture
def bob(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> Agents:
    email = "bob@example.com"
    return Agents(Session(make_client(), email), portal, engine, email)


def test_agents_require_a_session(make_client: ClientFactory) -> None:
    response = make_client().get("/agents")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_a_new_user_has_no_agents(alice: Agents) -> None:
    assert alice.listed() == []


def test_a_claude_ai_client_is_listed_as_claude(alice: Agents) -> None:
    alice.connect_new("Claude", CLAUDE_AI)
    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]


def test_a_claude_code_client_is_listed_as_claude_code(alice: Agents) -> None:
    alice.connect_new("Claude Code", CLAUDE_CODE)
    assert alice.listed() == [{"kind": "claude_code", "name": "Claude Code"}]


def test_a_chatgpt_client_is_listed_as_chatgpt(alice: Agents) -> None:
    alice.connect_new("ChatGPT", CHATGPT)
    assert alice.listed() == [{"kind": "chatgpt", "name": "ChatGPT"}]


def test_a_codex_client_is_listed_as_codex(alice: Agents) -> None:
    alice.connect_new("Codex", CODEX)
    assert alice.listed() == [{"kind": "codex", "name": "Codex"}]


def test_an_unknown_client_is_listed_as_other_under_its_own_name(
    alice: Agents,
) -> None:
    alice.connect_new("Cursor", CLAUDE_CODE)
    assert alice.listed() == [{"kind": "other", "name": "Cursor"}]


def test_every_agent_has_an_id(alice: Agents) -> None:
    alice.connect_new("Claude", CLAUDE_AI)
    alice.connect_new("Cursor", CLAUDE_CODE)

    assert alice.get().status_code == 200
    ids = [a["id"] for a in alice.get().json()]

    assert len({UUID(i) for i in ids}) == 2
    assert {agent_id for agent_id, _ in alice.stored_agents()} == {UUID(i) for i in ids}


def test_the_response_is_not_cached(alice: Agents) -> None:
    response = alice.get()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_connecting_the_same_client_twice_gives_one_agent(alice: Agents) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)

    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]
    assert len(alice.stored_agents()) == 1


def test_reconnecting_links_the_agent_to_the_newest_grant(alice: Agents) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)
    second = alice.connect(client, CLAUDE_AI)

    assert [grant for _, grant in alice.stored_agents()] == [second.value]


def test_reconnecting_keeps_the_agent_id(alice: Agents) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)
    before = alice.listed()
    assert before == [{"kind": "claude", "name": "Claude"}]
    id_before = alice.get().json()[0]["id"]

    alice.connect(client, CLAUDE_AI)

    assert alice.get().json()[0]["id"] == id_before


def test_two_different_clients_give_two_agents(alice: Agents) -> None:
    alice.connect_new("Claude", CLAUDE_AI)
    alice.connect_new("ChatGPT", CHATGPT)

    assert sorted(alice.listed(), key=lambda a: a["kind"]) == [
        {"kind": "chatgpt", "name": "ChatGPT"},
        {"kind": "claude", "name": "Claude"},
    ]


def test_a_revoked_grant_removes_the_agent(alice: Agents) -> None:
    grant = alice.connect_new("Claude", CLAUDE_AI)
    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]

    alice.revoke(grant)

    assert alice.listed() == []


def test_an_expired_refresh_token_removes_the_agent(alice: Agents) -> None:
    grant = alice.connect_new("Claude", CLAUDE_AI)

    alice.expire_refresh(grant)

    assert alice.listed() == []


def test_a_consumed_refresh_token_removes_the_agent(alice: Agents) -> None:
    grant = alice.connect_new("Claude", CLAUDE_AI)

    alice.consume_refresh(grant)

    assert alice.listed() == []


def test_an_authorization_without_the_code_exchange_is_not_connected(
    alice: Agents,
) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    alice.authorize(client, CLAUDE_AI)

    assert alice.listed() == []


def test_an_unfinished_reconnect_keeps_the_agent_connected(alice: Agents) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)

    alice.authorize(client, CLAUDE_AI)

    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]


def test_revoking_the_old_grant_keeps_the_agent_while_the_new_one_lives(
    alice: Agents,
) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    first = alice.connect(client, CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)

    alice.revoke(first)

    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]


def test_another_users_agents_are_not_visible(alice: Agents, bob: Agents) -> None:
    alice.connect_new("Claude", CLAUDE_AI)

    assert bob.listed() == []
    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]


def test_each_user_sees_only_their_own_connection_of_the_same_client(
    alice: Agents, bob: Agents
) -> None:
    client = alice.register("Claude", CLAUDE_AI)
    alice.connect(client, CLAUDE_AI)
    bob.connect(client, CLAUDE_AI)

    assert alice.listed() == [{"kind": "claude", "name": "Claude"}]
    assert bob.listed() == [{"kind": "claude", "name": "Claude"}]
