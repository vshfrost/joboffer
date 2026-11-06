"""Порти контексту identity: репозиторій користувачів і unit of work, що його відкриває."""

from typing import Protocol

from application.ports.unit_of_work import UnitOfWork
from domain.identity.email import Email
from domain.identity.external_identity import ExternalIdentity
from domain.identity.ids import UserId
from domain.identity.user import User


class UserRepository(Protocol):
    async def get(self, user_id: UserId) -> User:
        """Нема — `NotFound`."""
        ...

    async def find_by_email(self, email: Email) -> User | None: ...

    async def add(self, user: User) -> None:
        """Такий email уже є — `EmailTaken`."""
        ...


class ExternalIdentityRepository(Protocol):
    async def find(self, provider: str, subject: str) -> ExternalIdentity | None: ...

    async def add(self, identity: ExternalIdentity) -> None: ...


class IdentityUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def external_identities(self) -> ExternalIdentityRepository: ...
