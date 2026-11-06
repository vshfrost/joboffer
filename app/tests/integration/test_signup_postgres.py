"""Реєстрація на справжньому Postgres: сховище запитів, згода в users, гонка за запрошення, одна транзакція."""

import hashlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.legal import LegalDoc
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from domain.identity.email import Email
from domain.identity.ids import SignupRequestId, UserId
from domain.identity.password import PasswordHash
from domain.identity.session import TokenDigest
from domain.identity.signup_request import SignupDraft, SignupRequest, code_digest
from domain.identity.user import DisplayName, User
from infrastructure.db.unit_of_work import UnitOfWorkFactory, unit_of_work_factory
from tests.support.altcha import TEST_KEY, solve_challenge
from tests.support.fake_mailbox import FakeMailbox

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
PLAIN_PASSWORD = "Correct-Horse-9"
CODE = "483920"
TERMS = "2026-10-28"
CLEAN_TABLES = (
    "users CASCADE",
    "signup_requests",
    "signup_invites",
    "login_failures",
    "signup_limits",
    "altcha_solutions",
    "mail_sends",
)


@pytest.fixture
def uow(portal: BlockingPortal, engine: AsyncEngine) -> UnitOfWorkFactory:
    async def clean() -> None:
        async with engine.begin() as conn:
            for table in CLEAN_TABLES:
                await conn.execute(text(f"TRUNCATE {table}"))

    portal.call(clean)
    return unit_of_work_factory(engine)


def make_request(
    number: int = 1, *, email: str = "taras@example.com", now: datetime = NOW
) -> SignupRequest:
    request_id = SignupRequestId(UUID(int=number))
    return SignupRequest.issue(
        SignupDraft(
            email=Email(email),
            password_hash=PasswordHash(PASSWORD_HASH),
            display_name=DisplayName("Богдан"),
            invite_digest=TokenDigest.from_token("invite-token"),
            terms_version=TERMS,
        ),
        id=request_id,
        code=CODE,
        now=now,
    )


async def _add(uow: UnitOfWorkFactory, request: SignupRequest) -> None:
    async with uow() as tx:
        await tx.signup_requests.add(request)
        await tx.commit()


async def _get(uow: UnitOfWorkFactory, number: int) -> SignupRequest | None:
    async with uow() as tx:
        return await tx.signup_requests.get(SignupRequestId(UUID(int=number)))


def test_a_stored_request_is_read_back_equal(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    request = make_request()

    portal.call(_add, uow, request)

    assert portal.call(_get, uow, 1) == request


def test_an_unknown_request_is_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    assert portal.call(_get, uow, 99) is None


def test_the_database_holds_only_the_password_hash_and_the_code_digest(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, make_request())

    async def row() -> dict[str, Any]:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT * FROM signup_requests"))
            return dict(result.mappings().one())

    stored = portal.call(row)

    assert stored["password_hash"] == PASSWORD_HASH
    assert (
        stored["code_digest"]
        == hashlib.sha256(f"{UUID(int=1)}{CODE}".encode()).hexdigest()
    )
    text_values = " ".join(str(value) for value in stored.values())
    assert CODE not in text_values.replace(stored["code_digest"], "")
    assert PLAIN_PASSWORD not in text_values
    assert sorted(stored) == sorted(
        [
            "id", "email", "password_hash", "display_name", "invite_digest",
            "terms_version", "code_digest", "failed_attempts", "created_at",
            "sent_at", "expires_at",
        ]
    )  # fmt: skip


def test_one_request_per_email_the_new_one_replaces_the_old(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    portal.call(_add, uow, make_request(1))
    second = make_request(2)

    portal.call(_add, uow, second)

    assert portal.call(_get, uow, 1) is None
    assert portal.call(_get, uow, 2) == second


def test_save_updates_the_attempts_and_the_code(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    request = make_request()
    portal.call(_add, uow, request)
    later = NOW + timedelta(minutes=10)
    changed = request.failed().failed().with_new_code("111111", later).failed()

    async def save() -> None:
        async with uow() as tx:
            await tx.signup_requests.save(changed)
            await tx.commit()

    portal.call(save)

    stored = portal.call(_get, uow, 1)
    assert stored == changed
    assert stored is not None
    assert (stored.failed_attempts, stored.sent_at) == (1, later)
    assert stored.code_digest == code_digest(request.id, "111111")


def test_changes_without_commit_are_rolled_back(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    request = make_request()
    portal.call(_add, uow, request)

    async def save_without_commit() -> None:
        async with uow() as tx:
            await tx.signup_requests.save(request.failed())
            await tx.signup_requests.delete(request.id)

    portal.call(save_without_commit)

    assert portal.call(_get, uow, 1) == request


def test_delete_removes_the_request_and_ignores_an_unknown_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, make_request())

    async def delete() -> None:
        async with uow() as tx:
            await tx.signup_requests.delete(SignupRequestId(UUID(int=1)))
            await tx.signup_requests.delete(SignupRequestId(UUID(int=99)))
            await tx.commit()

    portal.call(delete)

    assert portal.call(_get, uow, 1) is None


def test_purge_expired_removes_only_requests_past_their_term(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    portal.call(_add, uow, make_request(1, email="old@example.com"))
    portal.call(
        _add,
        uow,
        make_request(2, email="fresh@example.com", now=NOW + timedelta(minutes=10)),
    )

    async def purge() -> None:
        async with uow() as tx:
            await tx.signup_requests.purge_expired(NOW + timedelta(minutes=15))
            await tx.commit()

    portal.call(purge)

    assert portal.call(_get, uow, 1) is None
    assert portal.call(_get, uow, 2) is not None


def test_a_user_keeps_the_accepted_terms(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    user = User.register(
        id=UserId(UUID(int=5)),
        email=Email("katya@example.com"),
        display_name=DisplayName("Наталя"),
        password_hash=PasswordHash(PASSWORD_HASH),
        now=NOW,
    ).accepting_terms(TERMS, NOW)

    async def roundtrip() -> User:
        async with uow() as tx:
            await tx.users.add(user)
            await tx.commit()
        async with uow() as tx:
            return await tx.users.get(user.id)

    stored = portal.call(roundtrip)

    assert (stored.terms_version, stored.terms_accepted_at) == (TERMS, NOW)


def test_a_user_without_terms_stays_without_them(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    user = User.register(
        id=UserId(UUID(int=6)),
        email=Email("old@example.com"),
        display_name=DisplayName("Давній"),
        password_hash=None,
        now=NOW,
    )

    async def roundtrip() -> User:
        async with uow() as tx:
            await tx.users.add(user)
            await tx.commit()
        async with uow() as tx:
            return await tx.users.get(user.id)

    stored = portal.call(roundtrip)

    assert (stored.terms_version, stored.terms_accepted_at) == (None, None)


def sql(
    portal: BlockingPortal, engine: AsyncEngine, statement: str, **params: Any
) -> list[Any]:
    async def run() -> list[Any]:
        async with engine.begin() as conn:
            result = await conn.execute(text(statement), params)
            return list(result.all()) if result.returns_rows else []

    return portal.call(run)


@pytest.fixture
def app_client(
    uow: UnitOfWorkFactory, database_url: str, mailbox: FakeMailbox
) -> Iterator[TestClient]:
    settings = Settings(
        environment="test",
        database_url=database_url,
        altcha_hmac_key=SecretStr(TEST_KEY),
        altcha_maxnumber=500,
        signup_mode="invite",
        mail_address="mailroom@example.com",
        gmail_client_id="id",
        gmail_client_secret=SecretStr("client-secret"),
        gmail_send_refresh_token=SecretStr("send-refresh"),
    )
    client = TestClient(
        create_app(settings, mail_transport=mailbox.transport()),
        base_url="https://testserver",
    )
    with client:
        yield client


@pytest.fixture
def mailbox() -> FakeMailbox:
    return FakeMailbox()


def register(client: TestClient, invite: str, email: str) -> str:
    legal = container_of(client.app).legal  # type: ignore[arg-type]
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": PLAIN_PASSWORD,
            "invite": invite,
            "terms_version": legal.get(LegalDoc.TERMS).version,
            "altcha": solve_challenge(**client.get("/auth/challenge").json()),
        },
    )
    assert response.status_code == 202, response.text
    return str(response.json()["signup_id"])


def new_invite(client: TestClient) -> str:
    invites = container_of(client.app).invites  # type: ignore[arg-type]
    assert client.portal is not None
    return client.portal.call(invites.create).token


def test_verify_creates_the_user_with_terms_burns_the_invite_and_removes_the_request(
    app_client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    invite = new_invite(app_client)
    signup_id = register(app_client, invite, "taras@example.com")
    legal = container_of(app_client.app).legal  # type: ignore[arg-type]

    response = app_client.post(
        "/auth/signup/verify", json={"signup_id": signup_id, "code": mailbox.codes()[0]}
    )

    users = sql(
        portal,
        engine,
        "SELECT email, password_hash, terms_version, terms_accepted_at FROM users",
    )
    invites = sql(portal, engine, "SELECT used_at FROM signup_invites")
    requests = sql(portal, engine, "SELECT 1 FROM signup_requests")
    sessions = sql(portal, engine, "SELECT 1 FROM sessions")
    assert response.status_code == 201
    ((email, password_hash, terms_version, accepted_at),) = users
    assert email == "taras@example.com"
    assert password_hash.startswith("$argon2")
    assert terms_version == legal.get(LegalDoc.TERMS).version
    assert abs(accepted_at - datetime.now(UTC)) < timedelta(minutes=5)
    assert invites[0][0] is not None
    assert requests == []
    assert len(sessions) == 1


def test_two_waiting_requests_on_one_invite_only_one_becomes_a_user(
    app_client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    invite = new_invite(app_client)
    first = register(app_client, invite, "first@example.com")
    second = register(app_client, invite, "second@example.com")
    codes = dict(zip(mailbox.to(), mailbox.codes(), strict=True))

    def verify(signup_id: str, email: str) -> int:
        return app_client.post(
            "/auth/signup/verify", json={"signup_id": signup_id, "code": codes[email]}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: verify(*args),
                [(first, "first@example.com"), (second, "second@example.com")],
            )
        )

    users = sql(portal, engine, "SELECT email FROM users")
    assert sorted(results) == [201, 409]
    assert len(users) == 1


def test_an_email_taken_while_waiting_rolls_the_invite_redemption_back(
    app_client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    invite = new_invite(app_client)
    signup_id = register(app_client, invite, "taras@example.com")
    sql(
        portal,
        engine,
        "INSERT INTO users (id, email, display_name, version, created_at) "
        "VALUES (:id, 'taras@example.com', 'Хтось', 1, now())",
        id=UUID(int=500),
    )

    response = app_client.post(
        "/auth/signup/verify", json={"signup_id": signup_id, "code": mailbox.codes()[0]}
    )

    assert (response.status_code, response.json()["code"]) == (409, "email_taken")
    assert sql(portal, engine, "SELECT used_at FROM signup_invites") == [(None,)]
    assert sql(portal, engine, "SELECT 1 FROM sessions") == []


def test_signup_limits_keep_the_hits_of_a_key_in_order_from_the_given_moment(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> tuple[list[datetime], list[datetime]]:
        async with uow() as tx:
            await tx.signup_limits.record("a", NOW + timedelta(minutes=5))
            await tx.signup_limits.record("a", NOW)
            await tx.signup_limits.record("b", NOW)
            await tx.commit()
        async with uow() as tx:
            return (
                await tx.signup_limits.since("a", NOW),
                await tx.signup_limits.since("a", NOW + timedelta(minutes=1)),
            )

    everything, later = portal.call(run)

    assert everything == [NOW, NOW + timedelta(minutes=5)]
    assert later == [NOW + timedelta(minutes=5)]


def test_signup_limits_purge_forgets_only_older_hits(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> list[datetime]:
        async with uow() as tx:
            await tx.signup_limits.record("a", NOW)
            await tx.signup_limits.record("a", NOW + timedelta(hours=1))
            await tx.signup_limits.purge(NOW + timedelta(minutes=30))
            await tx.commit()
        async with uow() as tx:
            return await tx.signup_limits.since("a", NOW - timedelta(days=1))

    assert portal.call(run) == [NOW + timedelta(hours=1)]


def test_login_failures_purge_leaves_signup_limits_alone(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> list[datetime]:
        async with uow() as tx:
            await tx.signup_limits.record("a", NOW)
            await tx.login_failures.record("a", NOW)
            await tx.login_failures.purge(NOW + timedelta(minutes=15))
            await tx.commit()
        async with uow() as tx:
            return await tx.signup_limits.since("a", NOW - timedelta(days=1))

    assert portal.call(run) == [NOW]
