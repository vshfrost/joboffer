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
from domain.identity.throttle import attempt_key, login_email_key

LOGIN_MAX_FAILURES = 5
# Усі клієнти разом: підбір пароля до одного акаунта з багатьох IP. Блок тимчасовий: спроби під
# час блоку не записуються, тож він знімається, щойно з вікна вийдуть старі невдачі, і нікого
# не блокує назавжди.
LOGIN_EMAIL_MAX_FAILURES = 20
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
        email_key = login_email_key(command.email)
        await self._ensure_not_throttled(key, email_key, now)
        try:
            user = await self._identity.authenticate(
                Authenticate(email=command.email, password=command.password)
            )
        except InvalidCredentials:
            async with self._unit_of_work() as uow:
                await uow.login_failures.record(key, now)
                await uow.login_failures.record(email_key, now)
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

    async def _ensure_not_throttled(
        self, key: str, email_key: str, now: datetime
    ) -> None:
        since = now - LOGIN_WINDOW
        async with self._unit_of_work() as uow:
            checks = (
                (await uow.login_failures.since(key, since), LOGIN_MAX_FAILURES),
                (
                    await uow.login_failures.since(email_key, since),
                    LOGIN_EMAIL_MAX_FAILURES,
                ),
            )
        waits = [
            math.ceil((failures[-maximum] + LOGIN_WINDOW - now).total_seconds())
            for failures, maximum in checks
            if len(failures) >= maximum
        ]
        if waits:
            # Блок знімається, коли з вікна вийде найстаріша з останніх `maximum` невдач.
            raise TooManyAttempts(
                "Забагато невдалих спроб входу. Спробуй пізніше",
                retry_after=max(1, *waits),
            )
