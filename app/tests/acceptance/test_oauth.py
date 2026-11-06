"""Кроки для features/oauth.feature: use cases OAuth + in-memory адаптери через портал."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given, parsers, scenarios, then, when

from application.contracts.oauth import (
    AuthorizationGranted,
    AuthorizationRequest,
    RegisterClient,
    TokenPair,
)
from application.oauth.use_cases import OAuthServices, OAuthUseCases
from application.ports.audit import AuditEvent
from domain.identity.ids import UserId
from domain.identity.session import TokenDigest
from domain.shared.errors import DomainError
from infrastructure.oauth.redirect import RedirectAllowlist
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.oauth import InMemoryOAuthUnitOfWork, InMemoryPending, OAuthStore
from tests.support.sessions import SequentialTokens

scenarios("features/oauth.feature")

RESOURCE = "https://agent.example/joboffer"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
USERS = {"Богдан": UserId(UUID(int=100)), "Наталя": UserId(UUID(int=200))}
CLIENT_IDS = {
    "Claude": "6f1c0a52-0000-4000-8000-000000000001",
    "Claude Code": "6f1c0a52-0000-4000-8000-000000000002",
    "Інший": "6f1c0a52-0000-4000-8000-000000000003",
    "Підроблений": "6f1c0a52-0000-4000-8000-000000000004",
    "Невідомий": "6f1c0a52-0000-4000-8000-0000000000ff",
}
DEFAULT_REDIRECT = "https://claude.ai/api/mcp/auth_callback"
UNITS = {"хвилин": "minutes", "годин": "hours", "днів": "days"}


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class World:
    """Що сталося в сценарії: помилки, запит на вхід, видані коди й токени за користувачами."""

    def __init__(
        self, portal: BlockingPortal, oauth: OAuthUseCases, redirects: dict[str, str]
    ) -> None:
        self.portal = portal
        self.oauth = oauth
        self.redirects = redirects
        self.errors: list[DomainError] = []
        self.rid: str | None = None
        self.granted: AuthorizationGranted | None = None
        self.granted_by_user: dict[str, AuthorizationGranted] = {}
        self.pairs: dict[str, list[TokenPair]] = {}

    def run[T](self, action: Callable[[], Awaitable[T]]) -> T | None:
        try:
            return self.portal.call(action)
        except DomainError as error:
            self.errors.append(error)
            return None

    def request(
        self,
        client: str,
        *,
        resource: str | None = RESOURCE,
    ) -> AuthorizationRequest:
        return AuthorizationRequest(
            client_id=CLIENT_IDS[client],
            redirect_uri=self.redirects.get(client, DEFAULT_REDIRECT),
            redirect_uri_provided_explicitly=True,
            state="state-xyz",
            code_challenge=CHALLENGE,
            resource=resource,
        )

    def begin(self, request: AuthorizationRequest) -> None:
        self.rid = self.run(lambda: self.oauth.begin_authorization(request))

    def last_pair(self, user: str) -> TokenPair:
        return self.pairs[user][-1]


@pytest.fixture
def store() -> OAuthStore:
    return OAuthStore()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


@pytest.fixture
def world(
    portal: BlockingPortal,
    store: OAuthStore,
    clock: FakeClock,
    ids: SequentialIds,
    audit: RecordingAudit,
) -> World:
    services = OAuthServices(
        clock=clock,
        ids=ids,
        tokens=SequentialTokens(),
        resource=RESOURCE,
        allowlist=RedirectAllowlist(),
        audit=audit,
    )
    oauth = OAuthUseCases(
        lambda: InMemoryOAuthUnitOfWork(store), InMemoryPending(), services
    )
    return World(portal, oauth, {})


def _register(world: World, client: str, redirect: str) -> None:
    world.redirects[client] = redirect
    command = RegisterClient(
        client_id=CLIENT_IDS[client],
        name=client,
        redirect_uris=(redirect,),
        metadata={"client_id": CLIENT_IDS[client], "client_name": client},
    )
    world.run(lambda: world.oauth.register_client(command))


@given(parsers.parse('клієнт "{client}" зареєстровано з адресою "{redirect}"'))
def registered_client(world: World, client: str, redirect: str) -> None:
    _register(world, client, redirect)
    assert world.errors == []


@when(parsers.parse('клієнт "{client}" реєструється з адресою "{redirect}"'))
def register_client(world: World, client: str, redirect: str) -> None:
    _register(world, client, redirect)


@when(parsers.parse('клієнт "{client}" просить доступ до resource "{resource}"'))
def ask_with_resource(world: World, client: str, resource: str) -> None:
    world.begin(world.request(client, resource=resource))


@when(parsers.parse('клієнт "{client}" просить доступ без resource'))
def ask_without_resource(world: World, client: str) -> None:
    world.begin(world.request(client, resource=None))


@when(parsers.parse('клієнт "{client}" просить доступ'))
def ask(world: World, client: str) -> None:
    world.begin(world.request(client))


@when(parsers.parse('користувач "{user}" входить за цим запитом'))
def sign_in(world: World, user: str) -> None:
    rid = world.rid
    assert rid is not None
    granted = world.run(lambda: world.oauth.complete_authorization(rid, USERS[user]))
    if granted is not None:
        world.granted = granted
        world.granted_by_user[user] = granted


@when(parsers.parse('клієнт "{client}" обмінює код на токени'))
def exchange_code(world: World, client: str) -> None:
    granted = world.granted
    assert granted is not None
    user = next(name for name, item in world.granted_by_user.items() if item is granted)
    pair = world.run(
        lambda: world.oauth.exchange_code(CLIENT_IDS[client], granted.code)
    )
    if pair is not None:
        world.pairs.setdefault(user, []).append(pair)


@when(parsers.parse('користувач "{user}" підключає клієнта "{client}"'))
def connect_client(world: World, user: str, client: str) -> None:
    world.begin(world.request(client))
    sign_in(world, user)
    exchange_code(world, client)
    assert world.errors == []


def _refresh(world: World, client: str, user: str, number: int) -> None:
    token = world.pairs[user][number - 1].refresh_token
    pair = world.run(lambda: world.oauth.exchange_refresh(CLIENT_IDS[client], token))
    if pair is not None:
        world.pairs[user].append(pair)


@when(parsers.parse('клієнт "{client}" оновлює токени за refresh користувача "{user}"'))
def refresh_latest(world: World, client: str, user: str) -> None:
    _refresh(world, client, user, len(world.pairs[user]))


@when(
    parsers.parse(
        'клієнт "{client}" оновлює токени за refresh номер {number:d} користувача "{user}"'
    )
)
def refresh_numbered(world: World, client: str, number: int, user: str) -> None:
    _refresh(world, client, user, number)


@when(parsers.parse('користувач "{user}" відкликає свій access-токен'))
def revoke_own(world: World, user: str) -> None:
    token = world.last_pair(user).access_token
    world.run(lambda: world.oauth.revoke(token))


@when(parsers.parse('хтось відкликає токен "{token}"'))
def revoke_unknown(world: World, token: str) -> None:
    world.run(lambda: world.oauth.revoke(token))


@when(parsers.parse("минає {amount:d} {unit}"))
def time_passes(clock: FakeClock, amount: int, unit: str) -> None:
    clock.advance(timedelta(**{UNITS[unit]: amount}))


@when("спрацьовує прибирання")
def purge(world: World) -> None:
    world.run(world.oauth.purge_expired)


@then("помилок не було")
def no_errors(world: World) -> None:
    assert world.errors == []


@then(parsers.parse('отримую помилку "{code}"'))
def error_with_code(world: World, code: str) -> None:
    assert world.errors, "помилки не було"
    assert world.errors[-1].code == code


@then(parsers.parse('клієнта "{client}" знайдено'))
def client_found(world: World, client: str) -> None:
    assert world.portal.call(world.oauth.find_client, CLIENT_IDS[client]) is not None


@then(parsers.parse('клієнта "{client}" не знайдено'))
def client_not_found(world: World, client: str) -> None:
    assert world.portal.call(world.oauth.find_client, CLIENT_IDS[client]) is None


@then(parsers.parse('запит на вхід описує клієнта "{client}" і хост "{host}"'))
def pending_description(world: World, client: str, host: str) -> None:
    rid = world.rid
    assert rid is not None
    view = world.portal.call(world.oauth.describe_pending, rid)
    assert view is not None
    assert (view.client_name, view.redirect_host) == (client, host)


@then("запит на вхід існує")
def pending_exists(world: World) -> None:
    rid = world.rid
    assert rid is not None
    assert world.portal.call(world.oauth.describe_pending, rid) is not None


@then("запит на вхід не існує")
def pending_gone(world: World) -> None:
    rid = world.rid
    assert rid is not None
    assert world.portal.call(world.oauth.describe_pending, rid) is None


@then(parsers.parse('токени видано на {seconds:d} секунд зі scope "{scope}"'))
def token_lifetime(world: World, seconds: int, scope: str) -> None:
    pair = world.pairs["Богдан"][-1]
    assert (pair.expires_in, pair.scope) == (seconds, scope)


def _acts_as(world: World, token: str) -> str | None:
    view = world.portal.call(world.oauth.verify_access, token)
    if view is None:
        return None
    return next(name for name, user_id in USERS.items() if user_id == view.user_id)


@then(parsers.parse('access-токен користувача "{user}" діє від імені "{actor}"'))
def access_acts_as(world: World, user: str, actor: str) -> None:
    assert _acts_as(world, world.last_pair(user).access_token) == actor


@then(
    parsers.parse(
        'access-токен номер {number:d} користувача "{user}" діє від імені "{actor}"'
    )
)
def numbered_access_acts_as(world: World, number: int, user: str, actor: str) -> None:
    assert _acts_as(world, world.pairs[user][number - 1].access_token) == actor


@then(parsers.parse('access-токен користувача "{user}" не діє'))
def access_dead(world: World, user: str) -> None:
    assert _acts_as(world, world.last_pair(user).access_token) is None


@then(parsers.parse('access-токен номер {number:d} користувача "{user}" не діє'))
def numbered_access_dead(world: World, number: int, user: str) -> None:
    assert _acts_as(world, world.pairs[user][number - 1].access_token) is None


def _refresh_alive(world: World, token: str, client: str = "Claude") -> bool:
    view = world.portal.call(world.oauth.load_refresh, CLIENT_IDS[client], token)
    return view is not None


@then(parsers.parse('refresh користувача "{user}" ще діє'))
def refresh_alive(world: World, user: str) -> None:
    assert _refresh_alive(world, world.last_pair(user).refresh_token)


@then(parsers.parse('refresh користувача "{user}" не діє'))
def refresh_dead(world: World, user: str) -> None:
    assert not _refresh_alive(world, world.last_pair(user).refresh_token)


@then(parsers.parse('refresh номер {number:d} користувача "{user}" не діє'))
def numbered_refresh_dead(world: World, number: int, user: str) -> None:
    assert not _refresh_alive(world, world.pairs[user][number - 1].refresh_token)


@then("гранти Богдана й Наталі різні")
def grants_differ(world: World) -> None:
    assert (
        world.granted_by_user["Богдан"].grant_id
        != world.granted_by_user["Наталя"].grant_id
    )


@then("у сховищі лише дайджести кодів і токенів")
def only_digests(world: World, store: OAuthStore) -> None:
    secrets = [world.granted_by_user["Богдан"].code]
    secrets += [
        secret
        for pair in world.pairs["Богдан"]
        for secret in (pair.access_token, pair.refresh_token)
    ]
    assert set(store.tokens) >= {TokenDigest.from_token(secret) for secret in secrets}
    dump = repr(store)
    assert all(secret not in dump for secret in secrets)


@then(parsers.parse('журнал аудиту містить події "{names}"'))
def audit_has_events(audit: RecordingAudit, names: str) -> None:
    recorded = [event.name for event in audit.events]
    assert [name for name in recorded if name in names.split(", ")] == names.split(", ")


@then("журнал аудиту не містить секретів")
def audit_without_secrets(world: World, audit: RecordingAudit) -> None:
    secrets = [world.rid or "", world.granted_by_user["Богдан"].code]
    secrets += [
        secret
        for pair in world.pairs["Богдан"]
        for secret in (pair.access_token, pair.refresh_token)
    ]
    dump = repr(audit.events)
    assert all(secret not in dump for secret in secrets)


@then(parsers.parse('у сховищі лишається лише refresh користувача "{user}"'))
def only_refresh_left(world: World, store: OAuthStore, user: str) -> None:
    refresh = TokenDigest.from_token(world.last_pair(user).refresh_token)
    assert set(store.tokens) == {refresh}


@then("у сховищі немає ні токенів, ні грантів")
def store_empty(store: OAuthStore) -> None:
    assert (store.tokens, store.grants) == ({}, {})
