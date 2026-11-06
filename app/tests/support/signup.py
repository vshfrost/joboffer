"""Адаптери реєстрації для core-тестів: запити в пам'яті, unit of work з commit, версія умов, коди."""

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from application.contracts.legal import LegalDoc, LegalDocument
from domain.identity.ids import SignupInviteId, SignupRequestId, UserId
from domain.identity.invite import SignupInvite
from domain.identity.signup_request import SignupRequest
from domain.identity.user import User
from tests.support.identity import InMemoryUsers
from tests.support.invites import InMemorySignupInvites

TERMS_VERSION = "2026-10-28"


class FakeLegalDocuments:
    """Поточна версія умов — `version`; решта документів мають ту саму."""

    def __init__(self, version: str = TERMS_VERSION) -> None:
        self.version = version

    def get(self, doc: LegalDoc) -> LegalDocument:
        return LegalDocument(doc=doc, version=self.version, text=f"Текст {doc.value}")


class SequentialCodes:
    """`100001`, `100002`, … — шестицифрові, однаково в кожному прогоні."""

    def __init__(self) -> None:
        self._next = 100001

    def new(self) -> str:
        value = f"{self._next:06d}"
        self._next += 1
        return value


class InMemorySignupRequests:
    def __init__(self, rows: dict[SignupRequestId, SignupRequest]) -> None:
        self._rows = rows

    async def add(self, request: SignupRequest) -> None:
        for request_id, row in list(self._rows.items()):
            if row.email == request.email:
                del self._rows[request_id]
        self._rows[request.id] = request

    async def get(self, request_id: SignupRequestId) -> SignupRequest | None:
        return self._rows.get(request_id)

    async def save(self, request: SignupRequest) -> None:
        self._rows[request.id] = request

    async def delete(self, request_id: SignupRequestId) -> None:
        self._rows.pop(request_id, None)

    async def purge_expired(self, now: datetime) -> None:
        for request_id, row in list(self._rows.items()):
            if row.expires_at <= now:
                del self._rows[request_id]


class InMemorySignupLimits:
    """Ліміти реєстрації (вікно до години): окремо від `login_failures`, які чистять вхід і запрошення."""

    def __init__(self, rows: list[tuple[str, datetime]]) -> None:
        self._rows = rows

    async def since(self, key: str, since: datetime) -> list[datetime]:
        return sorted(
            at for row_key, at in self._rows if row_key == key and at >= since
        )

    async def record(self, key: str, at: datetime) -> None:
        self._rows.append((key, at))

    async def purge(self, before: datetime) -> None:
        self._rows[:] = [row for row in self._rows if row[1] >= before]


@dataclass(slots=True)
class SignupStores:
    users: dict[UserId, User] = field(default_factory=dict)
    invites: dict[SignupInviteId, SignupInvite] = field(default_factory=dict)
    requests: dict[SignupRequestId, SignupRequest] = field(default_factory=dict)
    # Облік перевірок запрошень і входів: його ведуть інші use cases, реєстрація лише ділить сховище.
    failures: list[tuple[str, datetime]] = field(default_factory=list)
    limits: list[tuple[str, datetime]] = field(default_factory=list)


class InMemorySignupUnitOfWork:
    """Користувачі, запрошення, запити й ліміти реєстрації; зміни видно лише після `commit()`."""

    def __init__(self, stores: SignupStores) -> None:
        self._stores = stores
        self._staged: SignupStores | None = None

    def _open(self) -> SignupStores:
        if self._staged is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return self._staged

    @property
    def users(self) -> InMemoryUsers:
        return InMemoryUsers(self._open().users)

    @property
    def signup_invites(self) -> InMemorySignupInvites:
        return InMemorySignupInvites(self._open().invites)

    @property
    def signup_requests(self) -> InMemorySignupRequests:
        return InMemorySignupRequests(self._open().requests)

    @property
    def signup_limits(self) -> InMemorySignupLimits:
        return InMemorySignupLimits(self._open().limits)

    async def __aenter__(self) -> Self:
        stores = self._stores
        self._staged = SignupStores(
            dict(stores.users),
            dict(stores.invites),
            dict(stores.requests),
            list(stores.failures),
            list(stores.limits),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        staged, stores = self._open(), self._stores
        stores.users.clear()
        stores.users.update(staged.users)
        stores.invites.clear()
        stores.invites.update(staged.invites)
        stores.requests.clear()
        stores.requests.update(staged.requests)
        stores.failures[:] = staged.failures
        stores.limits[:] = staged.limits
