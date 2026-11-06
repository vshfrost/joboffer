"""Use cases OAuth-сервера: DCR, авторизація, обмін кодів і refresh, перевірка access-токена.

Код і токени видаються один раз і далі живуть лише в клієнта; сховище бачить sha256-дайджест.
Код і refresh одноразові: повторне пред'явлення використаного відкликає весь грант.
Кожна операція — свій unit of work.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from application.contracts.oauth import (
    AccessView,
    AuthorizationGranted,
    AuthorizationRequest,
    ClientView,
    CodeView,
    PendingView,
    RefreshView,
    RegisterClient,
    TokenPair,
)
from application.ports.audit import AuditEvent, AuditLog
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.oauth import OAuthUnitOfWork, PendingAuthorizations
from application.ports.redirects import RedirectPolicy
from application.ports.sessions import TokenGenerator
from domain.agents.agent import UserAgent
from domain.agents.classification import classify_agent
from domain.agents.ids import AgentId
from domain.identity.ids import GrantId, UserId
from domain.identity.session import TokenDigest
from domain.oauth.entities import (
    CodeBinding,
    Grant,
    OAuthClient,
    PendingAuthorization,
    StoredToken,
    TokenKind,
)
from domain.oauth.errors import (
    AuthorizationExpired,
    InvalidGrant,
    InvalidRedirectUri,
)
from domain.oauth.ids import ClientId
from domain.oauth.rules import (
    ACCESS_TTL,
    CODE_TTL,
    PENDING_TTL,
    REFRESH_TTL,
    SCOPE,
    ensure_resource,
)
from domain.shared.errors import InvalidValue

# Клієнт DCR, що за цей час так і не отримав гранту, більше не потрібен: `/register` відкритий усім.
UNUSED_CLIENT_AGE = timedelta(days=30)


@dataclass(frozen=True, slots=True, kw_only=True)
class OAuthServices:
    """Залежності, що не стосуються сховища: час, ID, секрети, resource сервера, allowlist."""

    clock: Clock
    ids: IdGenerator
    tokens: TokenGenerator
    resource: str
    allowlist: RedirectPolicy
    audit: AuditLog


def _client_id(raw: str) -> ClientId | None:
    try:
        return ClientId.parse(raw)
    except InvalidValue:
        return None


def _client_view(client: OAuthClient) -> ClientView:
    return ClientView(
        client_id=str(client.id),
        name=client.name,
        redirect_uris=client.redirect_uris,
        metadata=client.metadata,
    )


class OAuthUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], OAuthUnitOfWork],
        pending: PendingAuthorizations,
        services: OAuthServices,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._pending = pending
        self._services = services

    # --- клієнти (DCR) ----------------------------------------------------
    async def register_client(self, command: RegisterClient) -> ClientView:
        client = OAuthClient(
            id=ClientId.parse(command.client_id),
            name=command.name,
            redirect_uris=command.redirect_uris,
            metadata=command.metadata,
        )
        if not self._redirects_allowed(client):
            self._audit("register_rejected", client_name=command.name)
            raise InvalidRedirectUri("Адреса повернення не в allowlist цього сервера")
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            # Прибирання під час реєстрації: окремого планувальника для цього не потрібно.
            await uow.oauth_clients.delete_unused(now - UNUSED_CLIENT_AGE)
            await uow.oauth_clients.add(client, now)
            await uow.commit()
        self._audit("register", client_id=command.client_id, client_name=command.name)
        return _client_view(client)

    async def find_client(self, client_id: str) -> ClientView | None:
        """Невідомий клієнт чи клієнт із адресами, що вже поза allowlist, — `None`."""
        client = await self._find_client(client_id)
        return None if client is None else _client_view(client)

    # --- авторизація: /authorize → вхід користувача → код -------------------
    async def begin_authorization(self, request: AuthorizationRequest) -> str:
        """Перевіряє запит і запамʼятовує його; повертає rid для екрана входу."""
        # Клієнта, redirect_uri і scope уже перевірив SDK (/authorize); тут — лише resource.
        ensure_resource(request.resource, self._services.resource)
        rid = self._services.tokens.new()
        self._pending.put(
            rid,
            PendingAuthorization(
                client_id=ClientId.parse(request.client_id),
                binding=CodeBinding(
                    code_challenge=request.code_challenge,
                    redirect_uri=request.redirect_uri,
                    redirect_uri_provided_explicitly=request.redirect_uri_provided_explicitly,
                ),
                state=request.state,
                expires_at=self._services.clock.now() + PENDING_TTL,
            ),
        )
        return rid

    async def describe_pending(self, rid: str) -> PendingView | None:
        """Для екрана згоди: хто просить доступ і куди піде код. Живий запит — лише з rid."""
        pending = self._live_pending(rid)
        if pending is None:
            return None
        client = await self._find_client(str(pending.client_id))
        if client is None:
            return None
        return PendingView(
            client_name=(client.name or str(client.id))[:80],
            redirect_host=self._services.allowlist.host(pending.binding.redirect_uri),
        )

    async def complete_authorization(
        self, rid: str, user_id: UserId
    ) -> AuthorizationGranted:
        """Користувач увійшов: створює грант і видає код. Запит одноразовий."""
        pending = self._live_pending(rid, take=True)
        if pending is None:
            raise AuthorizationExpired(
                "Запит на вхід застарів. Почни підключення знову"
            )
        now = self._services.clock.now()
        grant = Grant(
            id=GrantId(self._services.ids.new()),
            user_id=user_id,
            client_id=pending.client_id,
            resource=self._services.resource,
            created_at=now,
        )
        code = self._services.tokens.new()
        async with self._unit_of_work() as uow:
            await uow.grants.add(grant)
            await uow.oauth_tokens.add(
                StoredToken(
                    digest=TokenDigest.from_token(code),
                    kind=TokenKind.CODE,
                    grant_id=grant.id,
                    expires_at=now + CODE_TTL,
                    code=pending.binding,
                )
            )
            client = await uow.oauth_clients.get(pending.client_id)
            if client is not None:
                identity = classify_agent(
                    str(client.id), client.name, client.redirect_uris
                )
                await uow.user_agents.upsert(
                    UserAgent(
                        id=AgentId(self._services.ids.new()),
                        user_id=user_id,
                        client_id=client.id,
                        grant_id=grant.id,
                        kind=identity.kind,
                        name=identity.name,
                        created_at=now,
                    )
                )
            await uow.commit()
        self._audit("login", grant=grant, redirect=pending.binding.redirect_uri)
        return AuthorizationGranted(
            redirect_uri=pending.binding.redirect_uri,
            code=code,
            state=pending.state,
            grant_id=grant.id,
        )

    # --- код авторизації ----------------------------------------------------
    async def load_code(self, client_id: str, code: str) -> CodeView | None:
        async with self._unit_of_work() as uow:
            found = await self._usable(uow, TokenKind.CODE, client_id, code)
        if found is None:
            return None
        stored, grant = found
        binding = stored.binding
        return CodeView(
            client_id=str(grant.client_id),
            code_challenge=binding.code_challenge,
            redirect_uri=binding.redirect_uri,
            redirect_uri_provided_explicitly=binding.redirect_uri_provided_explicitly,
            expires_at=stored.expires_at,
            resource=grant.resource,
            user_id=grant.user_id,
        )

    async def exchange_code(self, client_id: str, code: str) -> TokenPair:
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            found = await self._usable(uow, TokenKind.CODE, client_id, code)
            if found is None:
                raise InvalidGrant("Невірний код авторизації")
            stored, grant = found
            if not await uow.oauth_tokens.consume(stored.digest, now):
                await self._revoke_grant(uow, grant, "code_replay")
                await uow.commit()
                raise InvalidGrant("Код авторизації вже використано")
            pair = await self._issue(uow, grant)
            await uow.commit()
        return pair

    # --- refresh -----------------------------------------------------------
    async def load_refresh(self, client_id: str, token: str) -> RefreshView | None:
        async with self._unit_of_work() as uow:
            found = await self._usable(uow, TokenKind.REFRESH, client_id, token)
        if found is None:
            return None
        stored, grant = found
        return RefreshView(
            client_id=str(grant.client_id),
            expires_at=stored.expires_at,
            resource=grant.resource,
            user_id=grant.user_id,
        )

    async def exchange_refresh(self, client_id: str, token: str) -> TokenPair:
        """Ротація: старий refresh спалюється, видається нова пара. Scope перевіряє SDK."""
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            found = await self._usable(uow, TokenKind.REFRESH, client_id, token)
            if found is None:
                raise InvalidGrant("Невірний refresh-токен")
            stored, grant = found
            if not await uow.oauth_tokens.consume(stored.digest, now):
                await self._revoke_grant(uow, grant, "refresh_replay")
                await uow.commit()
                raise InvalidGrant("Refresh-токен вже використано")
            pair = await self._issue(uow, grant)
            await uow.commit()
        self._audit("refresh", grant=grant)
        return pair

    # --- access-токен ------------------------------------------------------
    async def verify_access(self, token: str) -> AccessView | None:
        """Від чийого імені діє токен: `user_id` гранту. Строк і resource токена перевіряє SDK (bearer)."""
        async with self._unit_of_work() as uow:
            stored = await uow.oauth_tokens.find_by_digest(
                TokenDigest.from_token(token)
            )
            if stored is None or stored.kind is not TokenKind.ACCESS:
                return None
            grant = await uow.grants.get(stored.grant_id)
        if grant is None or not grant.is_active:
            return None
        return AccessView(
            user_id=grant.user_id,
            grant_id=grant.id,
            client_id=str(grant.client_id),
            expires_at=stored.expires_at,
            resource=grant.resource,
        )

    async def revoke(self, token: str) -> None:
        """Відкликає грант токена: перестають діяти всі його токени. Невідомий токен — не помилка."""
        async with self._unit_of_work() as uow:
            stored = await uow.oauth_tokens.find_by_digest(
                TokenDigest.from_token(token)
            )
            if stored is None:
                return
            grant = await uow.grants.get(stored.grant_id)
            if grant is not None:
                await self._revoke_grant(uow, grant, "revoke")
            await uow.commit()

    async def purge_expired(self) -> None:
        """Прибирає прострочені коди й токени, гранти, що лишились без них, і клієнтів DCR без гранту."""
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            await uow.oauth_tokens.delete_expired(now)
            await uow.grants.delete_without_tokens()
            await uow.oauth_clients.delete_unused(now - UNUSED_CLIENT_AGE)
            await uow.commit()

    # --- внутрішнє ---------------------------------------------------------
    def _redirects_allowed(self, client: OAuthClient) -> bool:
        return bool(client.redirect_uris) and all(
            self._services.allowlist.allows(uri) for uri in client.redirect_uris
        )

    async def _find_client(self, raw_id: str) -> OAuthClient | None:
        client_id = _client_id(raw_id)
        if client_id is None:
            return None
        async with self._unit_of_work() as uow:
            client = await uow.oauth_clients.get(client_id)
        if client is None or not self._redirects_allowed(client):
            return None
        return client

    def _live_pending(
        self, rid: str, *, take: bool = False
    ) -> PendingAuthorization | None:
        pending = self._pending.take(rid) if take else self._pending.get(rid)
        if pending is None:
            return None
        if self._services.clock.now() >= pending.expires_at:
            self._pending.take(rid)
            return None
        return pending

    async def _usable(
        self, uow: OAuthUnitOfWork, kind: TokenKind, client_id: str, secret: str
    ) -> tuple[StoredToken, Grant] | None:
        """Код чи refresh цього клієнта, що ще можна пред'явити.

        Уже використаний — це повторне пред'явлення: грант відкликається (і це фіксується одразу).
        Чужий клієнт, прострочений і відкликаний виглядають як неіснуючі.
        """
        owner = _client_id(client_id)
        now = self._services.clock.now()
        stored = await uow.oauth_tokens.find_by_digest(TokenDigest.from_token(secret))
        if stored is None or stored.kind is not kind:
            return None
        grant = await uow.grants.get(stored.grant_id)
        if grant is None or owner is None or grant.client_id != owner:
            return None
        if stored.consumed_at is not None:
            await self._revoke_grant(uow, grant, f"{kind.value}_replay")
            await uow.commit()
            return None
        if not grant.is_active or stored.is_expired(now):
            return None
        return stored, grant

    async def _issue(self, uow: OAuthUnitOfWork, grant: Grant) -> TokenPair:
        now = self._services.clock.now()
        access, refresh = self._services.tokens.new(), self._services.tokens.new()
        for kind, secret, ttl in (
            (TokenKind.ACCESS, access, ACCESS_TTL),
            (TokenKind.REFRESH, refresh, REFRESH_TTL),
        ):
            await uow.oauth_tokens.add(
                StoredToken(
                    digest=TokenDigest.from_token(secret),
                    kind=kind,
                    grant_id=grant.id,
                    expires_at=now + ttl,
                )
            )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=int(ACCESS_TTL.total_seconds()),
            scope=SCOPE,
        )

    async def _revoke_grant(
        self, uow: OAuthUnitOfWork, grant: Grant, reason: str
    ) -> None:
        await uow.grants.revoke(grant.id, self._services.clock.now())
        self._audit(reason, grant=grant)

    def _audit(
        self,
        name: str,
        *,
        grant: Grant | None = None,
        client_id: str | None = None,
        client_name: str | None = None,
        redirect: str | None = None,
    ) -> None:
        self._services.audit.record(
            AuditEvent(
                name=name,
                user_id=None if grant is None else grant.user_id,
                grant_id=None if grant is None else grant.id,
                client_id=str(grant.client_id) if grant is not None else client_id,
                client_name=client_name,
                redirect=redirect,
            )
        )
