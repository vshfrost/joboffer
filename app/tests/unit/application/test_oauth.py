"""OAuth-сервер агента: DCR, авторизація, обмін кодів і refresh, перевірка access-токена."""

from datetime import timedelta
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal

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
from domain.oauth.errors import (
    AuthorizationExpired,
    InvalidGrant,
    InvalidRedirectUri,
    InvalidTarget,
)
from domain.oauth.redirect import CLAUDE_CALLBACK
from infrastructure.oauth.redirect import RedirectAllowlist
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.oauth import InMemoryOAuthUnitOfWork, InMemoryPending, OAuthStore
from tests.support.sessions import SequentialTokens

RESOURCE = "https://agent.example/joboffer"
CLIENT = "6f1c0a52-0000-4000-8000-000000000001"
OTHER_CLIENT = "6f1c0a52-0000-4000-8000-000000000002"
USER_A = UserId(UUID(int=100))
USER_B = UserId(UUID(int=200))
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
LOOPBACK = "http://127.0.0.1:53123/callback"


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


@pytest.fixture
def store() -> OAuthStore:
    return OAuthStore()


@pytest.fixture
def pending() -> InMemoryPending:
    return InMemoryPending()


@pytest.fixture
def oauth(
    store: OAuthStore,
    pending: InMemoryPending,
    clock: FakeClock,
    ids: SequentialIds,
    audit: RecordingAudit,
) -> OAuthUseCases:
    services = OAuthServices(
        clock=clock,
        ids=ids,
        tokens=SequentialTokens(),
        resource=RESOURCE,
        allowlist=RedirectAllowlist(),
        audit=audit,
    )
    return OAuthUseCases(lambda: InMemoryOAuthUnitOfWork(store), pending, services)


class Flow:
    """Сценарії поверх публічного інтерфейсу use cases (синхронна обгортка над порталом)."""

    def __init__(self, portal: BlockingPortal, oauth: OAuthUseCases) -> None:
        self.portal = portal
        self.oauth = oauth
        self._default_registered = False

    def _ensure_default_client(self) -> None:
        """Клієнт CLIENT реєструється при першому зверненні, а не у фікстурі: збій реєстрації — це збій тесту."""
        if not self._default_registered:
            self._default_registered = True
            self.register()

    def register(
        self, client_id: str = CLIENT, redirect: str = CLAUDE_CALLBACK
    ) -> None:
        self.portal.call(
            self.oauth.register_client,
            RegisterClient(
                client_id=client_id,
                name="Claude",
                redirect_uris=(redirect,),
                metadata={"client_id": client_id, "client_name": "Claude"},
            ),
        )

    def request(
        self,
        client_id: str = CLIENT,
        redirect: str = CLAUDE_CALLBACK,
        resource: str | None = RESOURCE,
    ) -> AuthorizationRequest:
        self._ensure_default_client()
        return AuthorizationRequest(
            client_id=client_id,
            redirect_uri=redirect,
            redirect_uri_provided_explicitly=True,
            state="state-xyz",
            code_challenge=CHALLENGE,
            resource=resource,
        )

    def authorize(
        self, user: UserId = USER_A, client_id: str = CLIENT
    ) -> AuthorizationGranted:
        self._ensure_default_client()
        rid = self.portal.call(
            self.oauth.begin_authorization, self.request(client_id=client_id)
        )
        return self.portal.call(self.oauth.complete_authorization, rid, user)

    def tokens(self, user: UserId = USER_A, client_id: str = CLIENT) -> TokenPair:
        granted = self.authorize(user, client_id)
        return self.portal.call(self.oauth.exchange_code, client_id, granted.code)


@pytest.fixture
def flow(portal: BlockingPortal, oauth: OAuthUseCases) -> Flow:
    return Flow(portal, oauth)


class TestClientRegistration:
    @pytest.mark.parametrize(
        "redirect",
        [
            "https://evil.example/api/mcp/auth_callback",
            "https://claude.ai@evil.example/api/mcp/auth_callback",
            "https://claude.ai:8443/api/mcp/auth_callback",
            "https://claude.ai/api/mcp/../auth_callback",
        ],
    )
    def test_redirect_outside_allowlist_is_rejected(
        self, portal: BlockingPortal, oauth: OAuthUseCases, redirect: str
    ) -> None:
        with pytest.raises(InvalidRedirectUri):
            Flow(portal, oauth).register(redirect=redirect)

    def test_every_redirect_must_be_allowed(
        self, portal: BlockingPortal, oauth: OAuthUseCases
    ) -> None:
        command = RegisterClient(
            client_id=CLIENT,
            name=None,
            redirect_uris=(CLAUDE_CALLBACK, "https://evil.example/cb"),
            metadata={},
        )
        with pytest.raises(InvalidRedirectUri):
            portal.call(oauth.register_client, command)

    def test_client_without_redirects_is_rejected(
        self, portal: BlockingPortal, oauth: OAuthUseCases
    ) -> None:
        command = RegisterClient(
            client_id=CLIENT, name=None, redirect_uris=(), metadata={}
        )
        with pytest.raises(InvalidRedirectUri):
            portal.call(oauth.register_client, command)

    def test_registered_client_is_found_with_its_metadata(
        self, portal: BlockingPortal, oauth: OAuthUseCases
    ) -> None:
        Flow(portal, oauth).register(redirect=LOOPBACK)

        view = portal.call(oauth.find_client, CLIENT)

        assert view is not None
        assert (view.client_id, view.name, view.redirect_uris) == (
            CLIENT,
            "Claude",
            (LOOPBACK,),
        )
        assert view.metadata == {"client_id": CLIENT, "client_name": "Claude"}

    @pytest.mark.parametrize(
        "client_id", [OTHER_CLIENT, "not-a-uuid", "", CLIENT.upper()]
    )
    def test_unknown_or_malformed_client_is_not_found(
        self, portal: BlockingPortal, oauth: OAuthUseCases, client_id: str
    ) -> None:
        Flow(portal, oauth).register()

        assert portal.call(oauth.find_client, client_id) is None

    def test_client_registered_before_the_allowlist_shrank_is_no_longer_found(
        self,
        portal: BlockingPortal,
        store: OAuthStore,
        pending: InMemoryPending,
        clock: FakeClock,
        ids: SequentialIds,
        audit: RecordingAudit,
    ) -> None:
        def build(allowlist: RedirectAllowlist) -> OAuthUseCases:
            services = OAuthServices(
                clock=clock,
                ids=ids,
                tokens=SequentialTokens(),
                resource=RESOURCE,
                allowlist=allowlist,
                audit=audit,
            )
            return OAuthUseCases(
                lambda: InMemoryOAuthUnitOfWork(store), pending, services
            )

        Flow(portal, build(RedirectAllowlist())).register(redirect=LOOPBACK)

        assert (
            portal.call(
                build(RedirectAllowlist((CLAUDE_CALLBACK,))).find_client, CLIENT
            )
            is None
        )


class TestRaces:
    def test_code_burned_by_a_concurrent_exchange_is_rejected_and_revokes_the_grant(
        self, flow: Flow, store: OAuthStore
    ) -> None:
        granted = flow.authorize()
        store.lose_consume_race = True

        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        grant = store.grants[granted.grant_id]
        assert not grant.is_active

    def test_refresh_burned_by_a_concurrent_exchange_is_rejected_and_revokes_the_grant(
        self, flow: Flow, store: OAuthStore
    ) -> None:
        granted = flow.authorize()
        pair = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)
        store.lose_consume_race = True

        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_refresh, CLIENT, pair.refresh_token)

        assert not store.grants[granted.grant_id].is_active


class TestAuthorization:
    def test_another_resource_is_invalid_target(self, flow: Flow) -> None:
        request = flow.request(resource="https://evil.example/joboffer")

        with pytest.raises(InvalidTarget):
            flow.portal.call(flow.oauth.begin_authorization, request)

    def test_request_without_resource_is_accepted(self, flow: Flow) -> None:
        rid = flow.portal.call(
            flow.oauth.begin_authorization, flow.request(resource=None)
        )

        assert rid

    def test_pending_request_tells_who_asks_and_where_the_code_goes(
        self, flow: Flow
    ) -> None:
        rid = flow.portal.call(flow.oauth.begin_authorization, flow.request())

        view = flow.portal.call(flow.oauth.describe_pending, rid)

        assert view is not None
        assert (view.client_name, view.redirect_host) == ("Claude", "claude.ai")

    def test_pending_request_of_a_client_that_vanished_describes_nothing(
        self, flow: Flow, store: OAuthStore
    ) -> None:
        rid = flow.portal.call(flow.oauth.begin_authorization, flow.request())
        store.clients.clear()

        assert flow.portal.call(flow.oauth.describe_pending, rid) is None

    def test_unknown_rid_describes_nothing(self, flow: Flow) -> None:
        assert flow.portal.call(flow.oauth.describe_pending, "no-such-rid") is None

    def test_completing_issues_a_code_for_the_clients_redirect_with_state(
        self, flow: Flow
    ) -> None:
        granted = flow.authorize()

        assert granted.redirect_uri == CLAUDE_CALLBACK
        assert granted.state == "state-xyz"
        assert granted.code

    def test_request_is_single_use(self, flow: Flow) -> None:
        rid = flow.portal.call(flow.oauth.begin_authorization, flow.request())
        flow.portal.call(flow.oauth.complete_authorization, rid, USER_A)

        with pytest.raises(AuthorizationExpired):
            flow.portal.call(flow.oauth.complete_authorization, rid, USER_A)
        assert flow.portal.call(flow.oauth.describe_pending, rid) is None

    def test_unknown_rid_cannot_be_completed(self, flow: Flow) -> None:
        with pytest.raises(AuthorizationExpired):
            flow.portal.call(flow.oauth.complete_authorization, "no-such-rid", USER_A)

    def test_request_expires_after_ten_minutes(
        self, flow: Flow, clock: FakeClock
    ) -> None:
        rid = flow.portal.call(flow.oauth.begin_authorization, flow.request())

        clock.advance(timedelta(minutes=9, seconds=59))
        assert flow.portal.call(flow.oauth.describe_pending, rid) is not None
        clock.advance(timedelta(seconds=1))

        assert flow.portal.call(flow.oauth.describe_pending, rid) is None
        with pytest.raises(AuthorizationExpired):
            flow.portal.call(flow.oauth.complete_authorization, rid, USER_A)


class TestCodeExchange:
    def test_valid_code_gives_a_token_pair_for_one_hour(self, flow: Flow) -> None:
        pair = flow.tokens()

        assert pair.expires_in == 3600
        assert pair.scope == "joboffer"
        assert pair.access_token != pair.refresh_token

    def test_loaded_code_carries_what_the_client_asked_for(self, flow: Flow) -> None:
        granted = flow.authorize()

        view = flow.portal.call(flow.oauth.load_code, CLIENT, granted.code)

        assert view is not None
        assert (
            view.client_id,
            view.code_challenge,
            view.redirect_uri,
            view.redirect_uri_provided_explicitly,
            view.resource,
            view.user_id,
        ) == (CLIENT, CHALLENGE, CLAUDE_CALLBACK, True, RESOURCE, USER_A)

    def test_code_is_valid_for_five_minutes(self, flow: Flow, clock: FakeClock) -> None:
        granted = flow.authorize()

        clock.advance(timedelta(minutes=4, seconds=59))
        assert flow.portal.call(flow.oauth.load_code, CLIENT, granted.code) is not None
        clock.advance(timedelta(seconds=1))

        assert flow.portal.call(flow.oauth.load_code, CLIENT, granted.code) is None
        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

    def test_code_of_another_client_looks_nonexistent(
        self, flow: Flow, portal: BlockingPortal, oauth: OAuthUseCases
    ) -> None:
        flow.register(OTHER_CLIENT, LOOPBACK)
        granted = flow.authorize()

        assert flow.portal.call(oauth.load_code, OTHER_CLIENT, granted.code) is None
        with pytest.raises(InvalidGrant):
            flow.portal.call(oauth.exchange_code, OTHER_CLIENT, granted.code)

    def test_unknown_code_is_rejected(self, flow: Flow) -> None:
        assert flow.portal.call(flow.oauth.load_code, CLIENT, "nope") is None
        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_code, CLIENT, "nope")

    def test_code_cannot_be_used_twice(self, flow: Flow) -> None:
        granted = flow.authorize()
        flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

    def test_replayed_code_revokes_what_was_issued_from_it(self, flow: Flow) -> None:
        granted = flow.authorize()
        pair = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        assert flow.portal.call(flow.oauth.verify_access, pair.access_token) is None
        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, pair.refresh_token)
            is None
        )


class TestAccessToken:
    def test_token_acts_on_behalf_of_the_user_who_logged_in(self, flow: Flow) -> None:
        granted = flow.authorize(USER_B)
        pair = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        view = flow.portal.call(flow.oauth.verify_access, pair.access_token)

        assert view is not None
        assert (
            view.user_id,
            view.grant_id,
            view.client_id,
            view.resource,
        ) == (
            USER_B,
            granted.grant_id,
            CLIENT,
            RESOURCE,
        )

    def test_token_of_user_a_never_acts_for_user_b(self, flow: Flow) -> None:
        pair_a = flow.tokens(USER_A)
        pair_b = flow.tokens(USER_B)

        view_a = flow.portal.call(flow.oauth.verify_access, pair_a.access_token)
        view_b = flow.portal.call(flow.oauth.verify_access, pair_b.access_token)

        assert view_a is not None
        assert view_b is not None
        assert (view_a.user_id, view_b.user_id) == (USER_A, USER_B)
        assert view_a.grant_id != view_b.grant_id

    def test_each_authorization_is_its_own_grant(self, flow: Flow) -> None:
        first = flow.authorize(USER_A)
        second = flow.authorize(USER_A)

        assert first.grant_id != second.grant_id

    @pytest.mark.parametrize("token", ["", "nope"])
    def test_unknown_token_acts_for_nobody(self, flow: Flow, token: str) -> None:
        assert flow.portal.call(flow.oauth.verify_access, token) is None

    def test_refresh_token_is_not_an_access_token(self, flow: Flow) -> None:
        pair = flow.tokens()

        assert flow.portal.call(flow.oauth.verify_access, pair.refresh_token) is None

    def test_code_is_not_an_access_token(self, flow: Flow) -> None:
        granted = flow.authorize()

        assert flow.portal.call(flow.oauth.verify_access, granted.code) is None

    def test_revoking_a_token_stops_the_whole_grant(self, flow: Flow) -> None:
        pair = flow.tokens()

        flow.portal.call(flow.oauth.revoke, pair.access_token)

        assert flow.portal.call(flow.oauth.verify_access, pair.access_token) is None
        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, pair.refresh_token)
            is None
        )

    def test_revoking_one_grant_leaves_the_other_users_grant_alone(
        self, flow: Flow
    ) -> None:
        pair_a = flow.tokens(USER_A)
        pair_b = flow.tokens(USER_B)

        flow.portal.call(flow.oauth.revoke, pair_a.access_token)

        assert (
            flow.portal.call(flow.oauth.verify_access, pair_b.access_token) is not None
        )

    def test_revoking_an_unknown_token_is_not_an_error(self, flow: Flow) -> None:
        flow.portal.call(flow.oauth.revoke, "nope")

    def test_revoking_a_token_whose_grant_is_gone_is_not_an_error(
        self, flow: Flow, store: OAuthStore
    ) -> None:
        pair = flow.tokens()
        store.grants.clear()

        flow.portal.call(flow.oauth.revoke, pair.access_token)


class TestRefresh:
    def test_refresh_gives_a_new_pair_for_the_same_user_and_grant(
        self, flow: Flow
    ) -> None:
        granted = flow.authorize(USER_B)
        first = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        second = flow.portal.call(
            flow.oauth.exchange_refresh, CLIENT, first.refresh_token
        )

        assert second.access_token not in (first.access_token, first.refresh_token)
        view = flow.portal.call(flow.oauth.verify_access, second.access_token)
        assert view is not None
        assert (view.user_id, view.grant_id) == (USER_B, granted.grant_id)

    def test_loaded_refresh_token_describes_its_grant(self, flow: Flow) -> None:
        pair = flow.tokens(USER_B)

        view = flow.portal.call(flow.oauth.load_refresh, CLIENT, pair.refresh_token)

        assert view is not None
        assert (view.client_id, view.resource, view.user_id) == (
            CLIENT,
            RESOURCE,
            USER_B,
        )

    def test_reused_old_refresh_is_rejected_and_revokes_the_grant(
        self, flow: Flow
    ) -> None:
        first = flow.tokens()
        second = flow.portal.call(
            flow.oauth.exchange_refresh, CLIENT, first.refresh_token
        )

        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, first.refresh_token)
            is None
        )
        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_refresh, CLIENT, first.refresh_token)

        assert flow.portal.call(flow.oauth.verify_access, second.access_token) is None
        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, second.refresh_token)
            is None
        )

    def test_refresh_of_another_client_looks_nonexistent(self, flow: Flow) -> None:
        flow.register(OTHER_CLIENT, LOOPBACK)
        pair = flow.tokens()

        assert (
            flow.portal.call(flow.oauth.load_refresh, OTHER_CLIENT, pair.refresh_token)
            is None
        )
        with pytest.raises(InvalidGrant):
            flow.portal.call(
                flow.oauth.exchange_refresh, OTHER_CLIENT, pair.refresh_token
            )

    def test_refresh_token_lives_thirty_days(
        self, flow: Flow, clock: FakeClock
    ) -> None:
        pair = flow.tokens()

        clock.advance(timedelta(days=29, hours=23, minutes=59, seconds=59))
        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, pair.refresh_token)
            is not None
        )
        clock.advance(timedelta(seconds=1))

        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, pair.refresh_token)
            is None
        )
        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_refresh, CLIENT, pair.refresh_token)

    def test_access_token_is_not_a_refresh_token(self, flow: Flow) -> None:
        pair = flow.tokens()

        assert (
            flow.portal.call(flow.oauth.load_refresh, CLIENT, pair.access_token) is None
        )


class TestSecretsAtRest:
    def test_store_holds_only_digests_of_codes_and_tokens(
        self, flow: Flow, store: OAuthStore
    ) -> None:
        granted = flow.authorize()
        pair = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)
        secrets = [granted.code, pair.access_token, pair.refresh_token]

        assert {token.digest for token in store.tokens.values()} >= {
            TokenDigest.from_token(secret) for secret in secrets
        }
        dump = repr(store)
        assert all(secret not in dump for secret in secrets)

    def test_audit_events_record_who_and_where_but_never_secrets(
        self, flow: Flow, audit: RecordingAudit
    ) -> None:
        rid = flow.portal.call(flow.oauth.begin_authorization, flow.request())
        granted = flow.portal.call(flow.oauth.complete_authorization, rid, USER_A)
        pair = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)
        flow.portal.call(flow.oauth.exchange_refresh, CLIENT, pair.refresh_token)
        flow.portal.call(flow.oauth.revoke, pair.access_token)

        names = [event.name for event in audit.events]
        assert names[:2] == ["register", "login"]
        assert "refresh" in names
        login = next(event for event in audit.events if event.name == "login")
        assert (login.user_id, login.grant_id, login.client_id, login.redirect) == (
            USER_A,
            granted.grant_id,
            CLIENT,
            CLAUDE_CALLBACK,
        )
        dump = repr(audit.events)
        for secret in (rid, granted.code, pair.access_token, pair.refresh_token):
            assert secret not in dump

    def test_replayed_code_is_audited(self, flow: Flow, audit: RecordingAudit) -> None:
        granted = flow.authorize()
        flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)
        with pytest.raises(InvalidGrant):
            flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)

        assert "code_replay" in [event.name for event in audit.events]

    def test_rejected_registration_is_audited(
        self, portal: BlockingPortal, oauth: OAuthUseCases, audit: RecordingAudit
    ) -> None:
        with pytest.raises(InvalidRedirectUri):
            Flow(portal, oauth).register(redirect="https://evil.example/cb")

        assert [event.name for event in audit.events] == ["register_rejected"]


class TestPurge:
    def test_purge_removes_expired_codes_and_tokens_but_keeps_live_ones(
        self, flow: Flow, store: OAuthStore, clock: FakeClock
    ) -> None:
        granted = flow.authorize()
        pair = flow.portal.call(flow.oauth.exchange_code, CLIENT, granted.code)
        clock.advance(timedelta(hours=2))

        flow.portal.call(flow.oauth.purge_expired)

        assert set(store.tokens) == {TokenDigest.from_token(pair.refresh_token)}
        assert len(store.grants) == 1

    def test_unused_code_leaves_no_grant_after_purge(
        self, flow: Flow, store: OAuthStore, clock: FakeClock
    ) -> None:
        flow.authorize()
        clock.advance(timedelta(minutes=6))

        flow.portal.call(flow.oauth.purge_expired)

        assert (store.tokens, store.grants) == ({}, {})


STALE_AGE = timedelta(days=30)


def test_unused_client_older_than_30_days_is_purged(
    flow: Flow, oauth: OAuthUseCases, clock: FakeClock, portal: BlockingPortal
) -> None:
    flow.register()
    clock.advance(STALE_AGE + timedelta(seconds=1))

    portal.call(oauth.purge_expired)

    assert portal.call(oauth.find_client, CLIENT) is None


def test_unused_client_younger_than_30_days_is_kept(
    flow: Flow, oauth: OAuthUseCases, clock: FakeClock, portal: BlockingPortal
) -> None:
    flow.register()
    clock.advance(STALE_AGE - timedelta(days=1))

    portal.call(oauth.purge_expired)

    assert portal.call(oauth.find_client, CLIENT) is not None


def test_client_that_has_a_grant_is_never_purged(
    flow: Flow, oauth: OAuthUseCases, clock: FakeClock, portal: BlockingPortal
) -> None:
    flow.authorize()
    clock.advance(STALE_AGE * 3)

    portal.call(oauth.purge_expired)

    assert portal.call(oauth.find_client, CLIENT) is not None


def test_registering_a_new_client_purges_the_stale_ones(
    flow: Flow, oauth: OAuthUseCases, clock: FakeClock, portal: BlockingPortal
) -> None:
    flow.register()
    clock.advance(STALE_AGE + timedelta(seconds=1))

    flow.register(client_id=OTHER_CLIENT)

    assert portal.call(oauth.find_client, CLIENT) is None
    assert portal.call(oauth.find_client, OTHER_CLIENT) is not None
