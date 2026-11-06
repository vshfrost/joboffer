"""Порти сесій: репозиторій сесій, облік невдалих входів, генератор токенів, unit of work."""

from datetime import datetime
from typing import Protocol

from application.ports.identity import IdentityUnitOfWork
from domain.identity.ids import SessionId
from domain.identity.session import Session, TokenDigest


class SessionRepository(Protocol):
    async def add(self, session: Session) -> None: ...

    async def find_by_digest(self, digest: TokenDigest) -> Session | None: ...

    async def touch(self, session_id: SessionId, at: datetime) -> None:
        """Оновлює `last_seen_at`."""
        ...

    async def delete(self, session_id: SessionId) -> None:
        """Нема такої — нічого не робить."""
        ...

    async def delete_expired(self, now: datetime) -> None:
        """Видаляє сесії, абсолютний строк яких минув."""
        ...


class LoginFailures(Protocol):
    async def since(self, key: str, since: datetime) -> list[datetime]:
        """Час невдач за ключем не раніше `since`, від найстаріших."""
        ...

    async def record(self, key: str, at: datetime) -> None: ...

    async def clear(self, key: str) -> None: ...

    async def purge(self, before: datetime) -> None:
        """Забуває невдачі старші за `before` (для всіх ключів)."""
        ...


class TokenGenerator(Protocol):
    def new(self) -> str:
        """Непередбачуваний токен сесії; генерує адаптер, не домен."""
        ...


class AuthUnitOfWork(IdentityUnitOfWork, Protocol):
    @property
    def sessions(self) -> SessionRepository: ...

    @property
    def login_failures(self) -> LoginFailures: ...
