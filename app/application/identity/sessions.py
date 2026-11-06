"""Use cases сесій: вхід із лімітом спроб, перевірка сесії за токеном, вихід.

Токен видається один раз і далі живе лише в cookie користувача; сховище бачить дайджест.
Кожен крок — свій unit of work: дорога перевірка пароля йде поза транзакцією.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from application.contracts.identity import Authenticate, GoogleClaims, UserView
from application.contracts.sessions import Login, SessionIssued, SessionView
from application.identity.use_cases import IdentityUseCases, user_view
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.sessions import AuthUnitOfWork, TokenGenerator
from domain.identity.errors import (
    NOT_AUTHENTICATED_MESSAGE,
    InvalidCredentials,
    NotAuthenticated,
    TooManyAttempts,
)
from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, SessionPolicy, TokenDigest
from domain.identity.throttle import attempt_key

LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW = timedelta(minutes=15)
TOKEN_MAX = 256


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionServices:
    """Залежності сесій, що не стосуються сховища: час, ID, токени, строки."""

    clock: Clock
    ids: IdGenerator
    tokens: TokenGenerator
    policy: SessionPolicy


def _usable(token: str) -> bool:
    return 0 < len(token) <= TOKEN_MAX


class SessionUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], AuthUnitOfWork],
        identity: IdentityUseCases,
        services: SessionServices,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._identity = identity
        self._services = services

    async def verify_login(self, command: Login) -> UserView:
        """Перевіряє email і пароль з лімітом спроб; сесії не видає (вхід без cookie, наприклад OAuth-гейт)."""
        now = self._services.clock.now()
        key = attempt_key(command.client, command.email)
        await self._ensure_not_throttled(key, now)
        try:
            user = await self._identity.authenticate(
                Authenticate(email=command.email, password=command.password)
            )
        except InvalidCredentials:
            async with self._unit_of_work() as uow:
                await uow.login_failures.record(key, now)
                await uow.commit()
            raise
        async with self._unit_of_work() as uow:
            await uow.login_failures.clear(key)
            # Прибирання під час входу: окремого планувальника для цього не потрібно.
            await uow.login_failures.purge(now - LOGIN_WINDOW)
            await uow.commit()
        return user

    async def login(self, command: Login) -> SessionIssued:
        return await self.open_session(await self.verify_login(command))

    async def open_session(self, user: UserView) -> SessionIssued:
        """Сесія для вже відомого користувача, без пароля: після підтвердження коду чи входу через Google."""
        now = self._services.clock.now()
        token = self._services.tokens.new()
        session = Session.start(
            id=SessionId(self._services.ids.new()),
            user_id=UserId.parse(user.id),
            token_digest=TokenDigest.from_token(token),
            now=now,
            policy=self._services.policy,
        )
        async with self._unit_of_work() as uow:
            await uow.sessions.delete_expired(now)
            await uow.sessions.add(session)
            await uow.commit()
        return SessionIssued(token=token, user=user, expires_at=session.expires_at)

    async def sign_in_with_google(self, claims: GoogleClaims) -> SessionIssued:
        """Вхід через Google: знаходить чи створює користувача й відкриває ту саму сесію, що й пароль."""
        return await self.open_session(await self._identity.sign_in_with_google(claims))

    async def identify(self, token: str) -> SessionView:
        """Сесія за токеном; активність посуває вікно простою. Будь-яка невдача — `NotAuthenticated`."""
        if not _usable(token):
            raise NotAuthenticated(NOT_AUTHENTICATED_MESSAGE)
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            session = await uow.sessions.find_by_digest(TokenDigest.from_token(token))
            if session is None or not session.is_active(now, self._services.policy):
                raise NotAuthenticated(NOT_AUTHENTICATED_MESSAGE)
            user = await uow.users.get(session.user_id)
            await uow.sessions.touch(session.id, now)
            await uow.commit()
        return SessionView(
            session_id=str(session.id),
            user=user_view(user),
            expires_at=session.expires_at,
        )

    async def logout(self, token: str) -> None:
        """Закриває сесію; невідомий токен і повторний вихід — не помилка."""
        if not _usable(token):
            return
        async with self._unit_of_work() as uow:
            session = await uow.sessions.find_by_digest(TokenDigest.from_token(token))
            if session is not None:
                await uow.sessions.delete(session.id)
            await uow.commit()

    async def _ensure_not_throttled(self, key: str, now: datetime) -> None:
        async with self._unit_of_work() as uow:
            failures = await uow.login_failures.since(key, now - LOGIN_WINDOW)
        if len(failures) < LOGIN_MAX_FAILURES:
            return
        # Блок знімається, коли з вікна вийде найстаріша з останніх п'яти невдач.
        unblocked_at = failures[-LOGIN_MAX_FAILURES] + LOGIN_WINDOW
        retry_after = max(1, math.ceil((unblocked_at - now).total_seconds()))
        raise TooManyAttempts(
            "Забагато невдалих спроб входу. Спробуй пізніше", retry_after=retry_after
        )
