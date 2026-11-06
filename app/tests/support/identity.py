"""In-memory адаптери identity для core-тестів: та сама семантика, що в Postgres (унікальний email, commit)."""

import hashlib
import hmac
from dataclasses import replace
from types import TracebackType
from typing import Self

from domain.identity.email import Email
from domain.identity.errors import EmailTaken
from domain.identity.external_identity import ExternalIdentity
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.identity.user import User
from domain.shared.errors import NotFound


class FakePasswordHasher:
    """Швидкий хешер для core-тестів: сіль-лічильник + sha256. Не криптографія."""

    PREFIX = "fake"

    def __init__(self) -> None:
        self._counter = 0

    @staticmethod
    def _digest(salt: str, raw: str) -> str:
        return hashlib.sha256(f"{salt}:{raw}".encode()).hexdigest()

    async def hash(self, raw: str) -> PasswordHash:
        self._counter += 1
        salt = f"{self._counter:04d}"
        return PasswordHash(f"{self.PREFIX}${salt}${self._digest(salt, raw)}")

    async def verify(self, raw: str, stored: PasswordHash | None) -> bool:
        if stored is None:
            return False
        parts = stored.value.split("$")
        if len(parts) != 3 or parts[0] != self.PREFIX:
            return False
        return hmac.compare_digest(parts[2], self._digest(parts[1], raw))


class InMemoryUsers:
    def __init__(self, rows: dict[UserId, User]) -> None:
        self._rows = rows

    async def get(self, user_id: UserId) -> User:
        if user_id not in self._rows:
            raise NotFound(f"Користувача {user_id} нема")
        return self._rows[user_id]

    async def find_by_email(self, email: Email) -> User | None:
        return next((user for user in self._rows.values() if user.email == email), None)

    async def add(self, user: User) -> None:
        if await self.find_by_email(user.email) is not None:
            raise EmailTaken("Користувач з таким email уже існує")
        self._rows[user.id] = replace(user, events=())


class InMemoryExternalIdentities:
    def __init__(self, rows: dict[tuple[str, str], ExternalIdentity]) -> None:
        self._rows = rows

    async def find(self, provider: str, subject: str) -> ExternalIdentity | None:
        return self._rows.get((provider, subject))

    async def add(self, identity: ExternalIdentity) -> None:
        self._rows[(identity.provider, identity.subject)] = identity


class InMemoryIdentityUnitOfWork:
    """Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

    def __init__(
        self,
        store: dict[UserId, User],
        identities: dict[tuple[str, str], ExternalIdentity] | None = None,
    ) -> None:
        self._store = store
        self._identities = {} if identities is None else identities
        self._staged: dict[UserId, User] | None = None
        self._staged_identities: dict[tuple[str, str], ExternalIdentity] = {}

    @property
    def users(self) -> InMemoryUsers:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryUsers(self._staged)

    @property
    def external_identities(self) -> InMemoryExternalIdentities:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemoryExternalIdentities(self._staged_identities)

    async def __aenter__(self) -> Self:
        self._staged = dict(self._store)
        self._staged_identities = dict(self._identities)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        self._store.clear()
        self._store.update(self._staged)
        self._identities.clear()
        self._identities.update(self._staged_identities)
