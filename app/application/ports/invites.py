"""Порти запрошень на реєстрацію: репозиторій і unit of work.

Ліміт перевірок веде той самий `LoginFailures`, що й вхід, під окремим ключем.
"""

from datetime import datetime
from typing import Protocol

from application.ports.sessions import LoginFailures
from application.ports.unit_of_work import UnitOfWork
from domain.identity.invite import SignupInvite
from domain.identity.session import TokenDigest


class SignupInviteRepository(Protocol):
    async def add(self, invite: SignupInvite) -> None: ...

    async def find_by_digest(self, digest: TokenDigest) -> SignupInvite | None: ...

    async def redeem(self, digest: TokenDigest, now: datetime) -> bool:
        """Атомарно позначає запрошення використаним; `True` лише тому, хто встиг першим."""
        ...


class InviteUnitOfWork(UnitOfWork, Protocol):
    @property
    def signup_invites(self) -> SignupInviteRepository: ...

    @property
    def login_failures(self) -> LoginFailures: ...
