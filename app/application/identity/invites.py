"""Use cases запрошень на реєстрацію: створення, перевірка з лімітом, погашення."""

import math
from collections.abc import Callable
from datetime import timedelta

from application.contracts.invites import CheckInvite, InviteIssued, InviteStatus
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.invites import InviteUnitOfWork
from application.ports.sessions import TokenGenerator
from domain.identity.errors import InviteInvalid, SignupClosed, TooManyAttempts
from domain.identity.ids import SignupInviteId
from domain.identity.invite import SignupInvite
from domain.identity.session import TokenDigest
from domain.identity.signup import SignupMode
from domain.identity.throttle import invite_check_key

INVITE_CHECK_MAX = 20
INVITE_CHECK_WINDOW = timedelta(minutes=15)
TOKEN_MAX = 256
# Однакове повідомлення на всі причини: відповідь не розкриває, чи запрошення існувало.
INVITE_INVALID_MESSAGE = "Запрошення недійсне"


def _usable(token: str) -> bool:
    return 0 < len(token) <= TOKEN_MAX


class SignupInviteUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], InviteUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        tokens: TokenGenerator,
        mode: SignupMode,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._tokens = tokens
        self._mode = mode

    async def create(self) -> InviteIssued:
        """Оператор створює запрошення; токен повертається один раз."""
        token = self._tokens.new()
        invite = SignupInvite.issue(
            id=SignupInviteId(self._ids.new()),
            token_digest=TokenDigest.from_token(token),
            now=self._clock.now(),
        )
        async with self._unit_of_work() as uow:
            await uow.signup_invites.add(invite)
            await uow.commit()
        return InviteIssued(token=token, expires_at=invite.expires_at)

    async def check(self, command: CheckInvite) -> InviteStatus:
        """Чи дійсне посилання. Закрита реєстрація → `SignupClosed`, ліміт → `TooManyAttempts`,
        будь-яка інша невдача → `InviteInvalid`."""
        self._ensure_open()
        now = self._clock.now()
        key = invite_check_key(command.client)
        async with self._unit_of_work() as uow:
            # Межа вікна виключна: рівно через `retry_after` секунд перевірка знову дозволена.
            checks = [
                at
                for at in await uow.login_failures.since(key, now - INVITE_CHECK_WINDOW)
                if at > now - INVITE_CHECK_WINDOW
            ]
            if len(checks) >= INVITE_CHECK_MAX:
                # Блок знімається, коли з вікна вийде найстаріша з останніх двадцяти перевірок.
                unblocked_at = checks[-INVITE_CHECK_MAX] + INVITE_CHECK_WINDOW
                retry_after = max(1, math.ceil((unblocked_at - now).total_seconds()))
                raise TooManyAttempts(
                    "Забагато перевірок запрошення. Спробуй пізніше",
                    retry_after=retry_after,
                )
            await uow.login_failures.record(key, now)
            # Прибирання під час перевірки: окремого планувальника для цього не потрібно.
            await uow.login_failures.purge(now - INVITE_CHECK_WINDOW)
            await uow.commit()
        invite = None if not _usable(command.token) else await self._find(command.token)
        if invite is None or not invite.is_usable(now):
            raise InviteInvalid(INVITE_INVALID_MESSAGE)
        return InviteStatus(valid=True, expires_at=invite.expires_at)

    async def redeem(self, token: str) -> None:
        """Погашає запрошення; хто не встиг першим, отримує `InviteInvalid`."""
        self._ensure_open()
        if not _usable(token):
            raise InviteInvalid(INVITE_INVALID_MESSAGE)
        async with self._unit_of_work() as uow:
            redeemed = await uow.signup_invites.redeem(
                TokenDigest.from_token(token), self._clock.now()
            )
            await uow.commit()
        if not redeemed:
            raise InviteInvalid(INVITE_INVALID_MESSAGE)

    def _ensure_open(self) -> None:
        if self._mode is SignupMode.CLOSED:
            raise SignupClosed("Реєстрація закрита")

    async def _find(self, token: str) -> SignupInvite | None:
        async with self._unit_of_work() as uow:
            return await uow.signup_invites.find_by_digest(
                TokenDigest.from_token(token)
            )
