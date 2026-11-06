"""In-memory адаптери сесій для core-тестів: та сама семантика, що в Postgres (commit, ізоляція ключів)."""

from datetime import datetime
from types import TracebackType
from typing import Self

from domain.identity.external_identity import ExternalIdentity
from domain.identity.ids import SessionId, UserId
from domain.identity.session import Session, TokenDigest
from domain.identity.user import User
from tests.support.identity import InMemoryExternalIdentities, InMemoryUsers


class SequentialTokens:
    """`token-1`, `token-2`, … — однаково в кожному прогоні."""

    def __init__(self) -> None:
        self._next = 1

    def new(self) -> str:
        value = f"token-{self._next}"
        self._next += 1
        return value


class InMemorySessions:
    def __init__(self, rows: dict[SessionId, Session]) -> None:
        self._rows = rows

    async def add(self, session: Session) -> None:
        self._rows[session.id] = session

    async def find_by_digest(self, digest: TokenDigest) -> Session | None:
        return next(
            (row for row in self._rows.values() if row.token_digest == digest), None
        )

    async def touch(self, session_id: SessionId, at: datetime) -> None:
        if session_id in self._rows:
            self._rows[session_id] = self._rows[session_id].seen(at)

    async def delete(self, session_id: SessionId) -> None:
        self._rows.pop(session_id, None)

    async def delete_expired(self, now: datetime) -> None:
        for session_id, row in list(self._rows.items()):
            if row.expires_at <= now:
                del self._rows[session_id]


class InMemoryLoginFailures:
    def __init__(self, rows: list[tuple[str, datetime]]) -> None:
        self._rows = rows

    async def since(self, key: str, since: datetime) -> list[datetime]:
        return sorted(
            at for row_key, at in self._rows if row_key == key and at >= since
        )

    async def record(self, key: str, at: datetime) -> None:
        self._rows.append((key, at))

    async def clear(self, key: str) -> None:
        self._rows[:] = [row for row in self._rows if row[0] != key]

    async def purge(self, before: datetime) -> None:
        self._rows[:] = [row for row in self._rows if row[1] >= before]


class InMemoryAuthUnitOfWork:
    """Користувачі, сесії й невдачі входу; зміни видно лише після `commit()`."""

    def __init__(
        self,
        users: dict[UserId, User],
        sessions: dict[SessionId, Session],
        failures: list[tuple[str, datetime]],
        identities: dict[tuple[str, str], ExternalIdentity] | None = None,
    ) -> None:
        self._stores = (users, sessions, failures)
        self._identities = {} if identities is None else identities
        self._staged_identities: dict[tuple[str, str], ExternalIdentity] = {}
        self._staged: (
            tuple[
                dict[UserId, User], dict[SessionId, Session], list[tuple[str, datetime]]
            ]
            | None
        ) = None

    def _open(
        self,
    ) -> tuple[
        dict[UserId, User], dict[SessionId, Session], list[tuple[str, datetime]]
    ]:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def users(self) -> InMemoryUsers:
        return InMemoryUsers(self._open()[0])

    @property
    def external_identities(self) -> InMemoryExternalIdentities:
        self._open()
        return InMemoryExternalIdentities(self._staged_identities)

    @property
    def sessions(self) -> InMemorySessions:
        return InMemorySessions(self._open()[1])

    @property
    def login_failures(self) -> InMemoryLoginFailures:
        return InMemoryLoginFailures(self._open()[2])

    async def __aenter__(self) -> Self:
        users, sessions, failures = self._stores
        self._staged = (dict(users), dict(sessions), list(failures))
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
        users, sessions, failures = self._open()
        stored_users, stored_sessions, stored_failures = self._stores
        stored_users.clear()
        stored_users.update(users)
        stored_sessions.clear()
        stored_sessions.update(sessions)
        stored_failures[:] = failures
        self._identities.clear()
        self._identities.update(self._staged_identities)
