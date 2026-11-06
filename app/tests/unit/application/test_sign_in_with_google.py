"""Вхід через Google лише для наявних: користувач за `sub` → за email (привʼязка); нового Google не створює."""

from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.identity import (
    Authenticate,
    CreateUser,
    GoogleClaims,
    UserView,
)
from application.contracts.sessions import SessionIssued
from application.identity.sessions import SessionServices, SessionUseCases
from application.identity.use_cases import IdentityUseCases
from domain.identity.errors import EmailRequired, NotAuthenticated
from domain.identity.external_identity import GOOGLE, ExternalIdentity
from domain.identity.ids import SessionId, UserId
from domain.identity.password import PasswordHash
from domain.identity.session import Session, SessionPolicy
from domain.identity.user import User
from tests.support.clock import FakeClock
from tests.support.identity import FakePasswordHasher
from tests.support.ids import SequentialIds
from tests.support.sessions import InMemoryAuthUnitOfWork, SequentialTokens

PASSWORD = "correct horse battery"


class SpyHasher(FakePasswordHasher):
    def __init__(self) -> None:
        super().__init__()
        self.verified_against: list[PasswordHash | None] = []

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        self.verified_against.append(stored)
        return await super().verify(raw, stored)


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.hasher = SpyHasher()
        self.users: dict[UserId, User] = {}
        self.sessions_store: dict[SessionId, Session] = {}
        self.identities: dict[tuple[str, str], ExternalIdentity] = {}
        failures: list[tuple[str, datetime]] = []

        def uow() -> InMemoryAuthUnitOfWork:
            return InMemoryAuthUnitOfWork(
                self.users, self.sessions_store, failures, self.identities
            )

        self.identity = IdentityUseCases(uow, clock, ids, self.hasher)
        policy = SessionPolicy(idle=timedelta(hours=12), absolute=timedelta(hours=48))
        self.sessions = SessionUseCases(
            uow,
            self.identity,
            SessionServices(
                clock=clock, ids=ids, tokens=SequentialTokens(), policy=policy
            ),
        )

    def sign_in(
        self,
        subject: str = "google-sub-1",
        email: str | None = "taras@example.com",
        *,
        verified: bool = True,
        name: str | None = "Богдан Прикладенко",
    ) -> UserView:
        claims = GoogleClaims(
            subject=subject, email=email, email_verified=verified, name=name
        )
        return self.portal.call(self.identity.sign_in_with_google, claims)

    def create_with_password(self, email: str = "taras@example.com") -> UserView:
        return self.portal.call(
            self.identity.create_user,
            CreateUser(email=email, display_name="Богдан", password=PASSWORD),
        )


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


class TestNoSelfRegistration:
    def test_unknown_email_is_refused_and_nothing_is_stored(self, world: World) -> None:
        with pytest.raises(EmailRequired):
            world.sign_in(email="stranger@example.com")

        assert (world.users, world.identities) == ({}, {})

    def test_unknown_email_does_not_open_a_session(self, world: World) -> None:
        claims = GoogleClaims(
            subject="s", email="stranger@example.com", email_verified=True, name=None
        )

        with pytest.raises(EmailRequired):
            world.portal.call(world.sessions.sign_in_with_google, claims)

        assert world.sessions_store == {}

    def test_other_users_do_not_let_an_unknown_email_in(self, world: World) -> None:
        world.create_with_password("katya@example.com")

        with pytest.raises(EmailRequired):
            world.sign_in(email="stranger@example.com")

        assert len(world.users) == 1
        assert world.identities == {}


class TestKnownUsers:
    def test_email_is_normalized_like_any_other(self, world: World) -> None:
        created = world.create_with_password()

        assert world.sign_in(email="  Taras@Example.COM ").id == created.id

    def test_known_sub_gives_the_same_user_again(self, world: World) -> None:
        world.create_with_password()
        first = world.sign_in()
        second = world.sign_in()

        assert first.id == second.id
        assert len(world.users) == 1
        assert len(world.identities) == 1

    def test_known_sub_with_a_changed_email_is_still_the_same_user(
        self, world: World
    ) -> None:
        world.create_with_password()
        first = world.sign_in()

        second = world.sign_in(email="new-address@example.com")

        assert second.id == first.id
        assert second.email == "taras@example.com"
        assert len(world.users) == 1

    def test_existing_email_gets_the_identity_linked_and_keeps_its_password(
        self, world: World
    ) -> None:
        created = world.create_with_password()

        signed_in = world.sign_in(email="TARAS@example.com")

        assert signed_in.id == created.id
        assert len(world.users) == 1
        assert str(world.identities[(GOOGLE, "google-sub-1")].user_id) == created.id
        authenticated = world.portal.call(
            world.identity.authenticate,
            Authenticate(email="taras@example.com", password=PASSWORD),
        )
        assert authenticated.id == created.id

    def test_two_google_accounts_with_different_emails_are_two_existing_users(
        self, world: World
    ) -> None:
        a = world.create_with_password("a@example.com")
        b = world.create_with_password("b@example.com")

        first = world.sign_in("sub-a", "a@example.com")
        second = world.sign_in("sub-b", "b@example.com")

        assert (first.id, second.id) == (a.id, b.id)


class TestEmailRequired:
    @pytest.mark.parametrize(
        ("email", "verified"),
        [
            (None, True),
            ("", True),
            ("   ", True),
            ("not-an-email", True),
            ("taras@example.com", False),
        ],
    )
    def test_no_usable_verified_email_means_no_sign_in_and_nothing_new_stored(
        self, world: World, email: str | None, verified: bool
    ) -> None:
        world.create_with_password()

        with pytest.raises(EmailRequired):
            world.sign_in(email=email, verified=verified)

        assert (len(world.users), world.identities) == (1, {})

    def test_unverified_email_of_an_existing_user_is_not_linked(
        self, world: World
    ) -> None:
        world.create_with_password()

        with pytest.raises(EmailRequired):
            world.sign_in(verified=False)

        assert world.identities == {}

    def test_a_known_sub_still_needs_a_verified_email(self, world: World) -> None:
        world.create_with_password()
        world.sign_in()

        with pytest.raises(EmailRequired):
            world.sign_in(verified=False)


class TestWebSession:
    def issue(self, world: World, **kwargs: object) -> SessionIssued:
        world.create_with_password()
        claims = GoogleClaims(
            subject="google-sub-1",
            email="taras@example.com",
            email_verified=True,
            name="Богдан",
        )
        return world.portal.call(world.sessions.sign_in_with_google, claims)

    def test_sign_in_opens_the_same_kind_of_session_as_the_password(
        self, world: World
    ) -> None:
        issued = self.issue(world)

        view = world.portal.call(world.sessions.identify, issued.token)

        assert view.user.email == "taras@example.com"
        assert view.user.id == issued.user.id

    def test_no_verified_email_opens_no_session(self, world: World) -> None:
        claims = GoogleClaims(
            subject="s", email="a@example.com", email_verified=False, name=None
        )

        with pytest.raises(EmailRequired):
            world.portal.call(world.sessions.sign_in_with_google, claims)

        assert world.sessions_store == {}

    def test_session_stores_only_the_token_digest(self, world: World) -> None:
        issued = self.issue(world)

        with pytest.raises(NotAuthenticated):
            world.portal.call(world.sessions.identify, "token-unknown")
        (stored,) = world.sessions_store.values()
        assert issued.token not in repr(stored)
