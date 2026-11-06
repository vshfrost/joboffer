"""Онбординг через HTTP наскрізь: сесія й CSRF, кроки з реальних даних у Postgres, підказки на сервері,
невідома підказка, ізоляція користувачів."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor, Channel, Scope
from bootstrap.api import container_of
from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.entities import Grant, OAuthClient, StoredToken, TokenKind
from domain.oauth.ids import ClientId
from infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from tests.integration.test_profile_http import (
    PASSWORD,
    ClientFactory,
    Session,
    make_client,
)
from tests.support.images import FRAME, jpeg

__all__ = ["make_client"]

KEYS = ["goal", "locations", "contacts", "claude", "original_cv", "photo", "mail"]
NOW = datetime.now(UTC)
_ids = iter(range(0xA000, 0xB000))


def _uuid() -> UUID:
    return UUID(int=next(_ids))


class Onboarding:
    def __init__(
        self,
        session: Session,
        portal: BlockingPortal,
        engine: AsyncEngine,
        email: str,
    ) -> None:
        self.session = session
        self.client = session.client
        self._portal = portal
        self._engine = engine
        self._email = email

    def get(self) -> httpx2.Response:
        response = self.client.get("/onboarding")
        assert response.status_code == 200, response.text
        return response

    def post(self, key: str, action: str, *, csrf: bool = True) -> httpx2.Response:
        return self.client.post(
            f"/onboarding/tips/{key}/{action}",
            headers=self.session.csrf if csrf else {},
        )

    def done(self) -> list[str]:
        return [s["key"] for s in self.get().json()["steps"] if s["done"]]

    def seen(self) -> list[str]:
        return [t["key"] for t in self.get().json()["tips"] if t["seen"]]

    def dismissed(self) -> list[str]:
        return [t["key"] for t in self.get().json()["tips"] if t["dismissed"]]

    def put(self, section: str, body: object) -> None:
        response = self.client.put(
            f"/profile/{section}", json=body, headers=self.session.csrf
        )
        assert response.status_code == 200, response.text

    def user(self) -> UserId:
        async def run() -> UserId:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                return UserId(row.scalar_one())

        return self._portal.call(run)

    def actor(self) -> Actor:
        return Actor(
            user_id=self.user(),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def in_db(self, work: Callable[[SqlAlchemyUnitOfWork], Awaitable[None]]) -> None:
        factory = container_of(self.client.app).unit_of_work  # type: ignore[arg-type]

        async def run() -> None:
            async with factory() as tx:
                await work(tx)
                await tx.commit()

        self._portal.call(run)

    def connect_claude(
        self, *, expires: timedelta = timedelta(days=30), consumed: bool = False
    ) -> GrantId:
        user = self.user()
        grant_id = GrantId(_uuid())
        client_id = ClientId(_uuid())

        async def work(tx: SqlAlchemyUnitOfWork) -> None:
            await tx.oauth_clients.add(
                OAuthClient(
                    id=client_id,
                    name="Claude",
                    redirect_uris=("https://claude.ai/cb",),
                    metadata={},
                )
            )
            await tx.grants.add(
                Grant(
                    id=grant_id,
                    user_id=user,
                    client_id=client_id,
                    resource="https://example.test/mcp",
                    created_at=NOW,
                )
            )
            for kind in (TokenKind.ACCESS, TokenKind.REFRESH):
                digest = TokenDigest.from_token(f"{kind}-{grant_id}")
                await tx.oauth_tokens.add(
                    StoredToken(
                        digest=digest,
                        kind=kind,
                        grant_id=grant_id,
                        expires_at=NOW + expires,
                        consumed_at=(
                            NOW if consumed and kind is TokenKind.REFRESH else None
                        ),
                    )
                )

        self.in_db(work)
        return grant_id

    def revoke_claude(self, grant_id: GrantId) -> None:
        async def work(tx: SqlAlchemyUnitOfWork) -> None:
            await tx.grants.revoke(grant_id, NOW)

        self.in_db(work)

    def save_original_cv(self) -> None:
        facts = container_of(self.client.app).facts  # type: ignore[arg-type]
        self._portal.call(
            facts.save_original_cv, self.actor(), "Alice Example\nPython", "cv.pdf"
        )

    def upload_photo(self) -> None:
        response = self.client.post(
            "/photos",
            files={"file": ("p.jpg", jpeg(*FRAME), "image/jpeg")},
            headers=self.session.csrf,
        )
        assert response.status_code == 201, response.text

    def open_mail_address(self) -> None:
        user = self.user()

        async def work(tx: SqlAlchemyUnitOfWork) -> None:
            await tx.mail_inboxes.ensure(user)

        self.in_db(work)


@pytest.fixture
def alice(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> Onboarding:
    email = "alice@example.com"
    return Onboarding(Session(make_client(), email), portal, engine, email)


@pytest.fixture
def bob(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> Onboarding:
    email = "bob@example.com"
    return Onboarding(Session(make_client(), email), portal, engine, email)


def contacts(email: str) -> dict[str, str]:
    return {
        "full_name": "Alice Example",
        "email": email,
        "phone": "",
        "linkedin_url": "",
        "city": "",
        "github_url": "",
        "work_authorization": "",
    }


def fill_required(who: Onboarding) -> None:
    who.put(
        "target",
        {
            "roles": ["Backend Developer"],
            "seniority": [],
            "min_salary_eur": None,
            "target_domains": [],
        },
    )
    who.put(
        "locations",
        {
            "work_modes": [],
            "locations": [
                {"place": "Valencia", "aliases": [], "work_modes": ["remote"]}
            ],
            "include_unknown_mode": True,
            "relocation": False,
        },
    )
    who.put("contacts", contacts("alice@example.com"))
    who.connect_claude()
    who.save_original_cv()


# --- доступ -----------------------------------------------------------------------------------


def test_every_route_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    for response in (
        client.get("/onboarding"),
        client.post("/onboarding/tips/goal/seen"),
        client.post("/onboarding/tips/goal/dismiss"),
    ):
        assert (response.status_code, response.json().get("code")) == (
            401,
            "not_authenticated",
        )


@pytest.mark.parametrize("action", ["seen", "dismiss"])
def test_a_tip_action_without_the_csrf_token_is_403_and_changes_nothing(
    alice: Onboarding, action: str
) -> None:
    response = alice.post("goal", action, csrf=False)
    assert (response.status_code, response.json().get("code")) == (403, "csrf_failed")
    assert alice.seen() == []
    assert alice.dismissed() == []


# --- кроки ------------------------------------------------------------------------------------


def test_a_new_user_has_every_step_open_and_no_tips_seen(alice: Onboarding) -> None:
    response = alice.get()
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "steps": [
            {"key": key, "done": False, "optional": key in {"photo", "mail"}}
            for key in KEYS
        ],
        "tips": [{"key": key, "seen": False, "dismissed": False} for key in KEYS],
        "complete": False,
    }


def test_steps_follow_the_real_data_one_by_one(alice: Onboarding) -> None:
    alice.put(
        "target",
        {
            "roles": ["Backend Developer"],
            "seniority": [],
            "min_salary_eur": None,
            "target_domains": [],
        },
    )
    assert alice.done() == ["goal"]
    alice.put(
        "locations",
        {
            "work_modes": [],
            "locations": [
                {"place": "Valencia", "aliases": [], "work_modes": ["remote"]}
            ],
            "include_unknown_mode": True,
            "relocation": False,
        },
    )
    assert alice.done() == ["goal", "locations"]
    alice.put("contacts", contacts("a@example.com"))
    assert alice.done() == ["goal", "locations", "contacts"]
    grant = alice.connect_claude()
    assert alice.done() == ["goal", "locations", "contacts", "claude"]
    alice.save_original_cv()
    assert alice.done() == ["goal", "locations", "contacts", "claude", "original_cv"]
    assert alice.get().json()["complete"] is True
    alice.upload_photo()
    alice.open_mail_address()
    assert alice.done() == KEYS
    alice.revoke_claude(grant)
    assert "claude" not in alice.done()
    assert alice.get().json()["complete"] is False


def test_a_revoked_grant_does_not_count(alice: Onboarding) -> None:
    alice.revoke_claude(alice.connect_claude())
    assert alice.done() == []


def test_a_grant_with_an_expired_refresh_token_does_not_count(
    alice: Onboarding,
) -> None:
    alice.connect_claude(expires=timedelta(days=-1))
    assert alice.done() == []


def test_a_grant_with_a_used_refresh_token_does_not_count(alice: Onboarding) -> None:
    alice.connect_claude(consumed=True)
    assert alice.done() == []


def test_photo_and_mail_are_optional_for_completion(alice: Onboarding) -> None:
    fill_required(alice)
    body = alice.get().json()
    assert body["complete"] is True
    assert [s["key"] for s in body["steps"] if s["done"] and s["optional"]] == []


def test_a_deleted_photo_reopens_its_step(alice: Onboarding) -> None:
    alice.upload_photo()
    assert alice.done() == ["photo"]
    response = alice.client.delete("/photos/1", headers=alice.session.csrf)
    assert response.status_code == 204
    assert alice.done() == []


# --- підказки ---------------------------------------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_a_tip_is_marked_seen_and_stays_seen_after_a_new_login(
    alice: Onboarding, make_client: ClientFactory, key: str
) -> None:
    response = alice.post(key, "seen")
    assert (response.status_code, response.content) == (204, b"")
    other_browser = make_client()
    login = other_browser.post(
        "/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    body = other_browser.get("/onboarding").json()
    assert [t["key"] for t in body["tips"] if t["seen"]] == [key]
    assert [t["key"] for t in body["tips"] if t["dismissed"]] == []


def test_dismissing_a_tip_marks_it_seen_and_dismissed(alice: Onboarding) -> None:
    response = alice.post("claude", "dismiss")
    assert (response.status_code, response.content) == (204, b"")
    assert alice.seen() == ["claude"]
    assert alice.dismissed() == ["claude"]


def test_repeating_a_tip_action_changes_nothing(alice: Onboarding) -> None:
    for action in ("seen", "dismiss", "seen", "dismiss"):
        assert alice.post("goal", action).status_code == 204
    assert (alice.seen(), alice.dismissed()) == (["goal"], ["goal"])


def test_a_tip_does_not_close_its_step(alice: Onboarding) -> None:
    alice.post("goal", "seen")
    alice.post("claude", "dismiss")
    assert alice.done() == []


@pytest.mark.parametrize("action", ["seen", "dismiss"])
def test_an_unknown_tip_is_404_and_nothing_is_saved(
    alice: Onboarding, action: str
) -> None:
    response = alice.post("nope", action)
    assert (response.status_code, response.json().get("code")) == (404, "not_found")
    assert alice.seen() == []


# --- ізоляція ---------------------------------------------------------------------------------


def test_another_users_data_and_tips_do_not_count(
    alice: Onboarding, bob: Onboarding
) -> None:
    fill_required(alice)
    alice.upload_photo()
    alice.open_mail_address()
    alice.post("goal", "seen")
    alice.post("claude", "dismiss")
    body = bob.get().json()
    assert [s["key"] for s in body["steps"] if s["done"]] == []
    assert body["complete"] is False
    assert bob.seen() == []
    assert bob.dismissed() == []


def test_a_tip_action_of_one_user_does_not_touch_the_other(
    alice: Onboarding, bob: Onboarding
) -> None:
    alice.post("goal", "dismiss")
    bob.post("goal", "seen")
    assert (alice.seen(), alice.dismissed()) == (["goal"], ["goal"])
    assert (bob.seen(), bob.dismissed()) == (["goal"], [])
