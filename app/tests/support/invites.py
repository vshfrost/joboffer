"""In-memory адаптери запрошень для core-тестів: та сама семантика, що в Postgres (commit, одноразове погашення)."""

from dataclasses import replace
from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.ids import SignupInviteId
from domain.identity.invite import SignupInvite
from domain.identity.session import TokenDigest
from tests.support.sessions import InMemoryLoginFailures


class InMemorySignupInvites:
    def __init__(self, rows: dict[SignupInviteId, SignupInvite]) -> None:
        self._rows = rows

    async def add(self, invite: SignupInvite) -> None:
        self._rows[invite.id] = invite

    async def find_by_digest(self, digest: TokenDigest) -> SignupInvite | None:
        return next(
            (row for row in self._rows.values() if row.token_digest == digest), None
        )

    async def redeem(self, digest: TokenDigest, now: datetime) -> bool:
        invite = await self.find_by_digest(digest)
        if invite is None or not invite.is_usable(now):
            return False
        self._rows[invite.id] = replace(invite, used_at=now)
        return True


class InMemoryInviteUnitOfWork:
    """Запрошення й облік перевірок; зміни видно лише після `commit()`."""

    def __init__(
        self,
        invites: dict[SignupInviteId, SignupInvite],
        failures: list[tuple[str, datetime]],
    ) -> None:
        self._stores = (invites, failures)
        self._staged: (
            tuple[dict[SignupInviteId, SignupInvite], list[tuple[str, datetime]]] | None
        ) = None

    def _open(
        self,
    ) -> tuple[dict[SignupInviteId, SignupInvite], list[tuple[str, datetime]]]:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def signup_invites(self) -> InMemorySignupInvites:
        return InMemorySignupInvites(self._open()[0])

    @property
    def login_failures(self) -> InMemoryLoginFailures:
        return InMemoryLoginFailures(self._open()[1])

    async def __aenter__(self) -> Self:
        invites, failures = self._stores
        self._staged = (dict(invites), list(failures))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        invites, failures = self._open()
        stored_invites, stored_failures = self._stores
        stored_invites.clear()
        stored_invites.update(invites)
        stored_failures[:] = failures
