"""Порти реєстрації: сховище запитів, генератор кодів і unit of work.

Користувач, запрошення й облік лімітів — у тому ж unit of work: підтвердження коду
гасить запрошення, створює користувача й видаляє запит в одній транзакції.
"""

from datetime import datetime
from typing import Protocol

from application.ports.identity import UserRepository
from application.ports.invites import SignupInviteRepository
from application.ports.unit_of_work import UnitOfWork
from domain.identity.ids import SignupRequestId
from domain.identity.signup_request import SignupRequest


class CodeGenerator(Protocol):
    def new(self) -> str:
        """Шестицифровий код з ведучими нулями; генерує адаптер, не домен."""
        ...


class SignupRequestRepository(Protocol):
    async def add(self, request: SignupRequest) -> None:
        """Один запит на email: наявний запит з тим самим email замінюється."""
        ...

    async def get(self, request_id: SignupRequestId) -> SignupRequest | None:
        """Читає запит і блокує його до кінця транзакції: паралельні спроби коду йдуть по черзі."""
        ...

    async def save(self, request: SignupRequest) -> None:
        """Оновлює наявний запит за id."""
        ...

    async def delete(self, request_id: SignupRequestId) -> None:
        """Нема такого — нічого не робить."""
        ...

    async def purge_expired(self, now: datetime) -> None:
        """Видаляє запити, чий строк коду минув."""
        ...


class SignupLimits(Protocol):
    """Ліміти реєстрації з вікном до години. Окремо від `LoginFailures`: ті чистять вхід і перевірка
    запрошення кожні 15 хвилин, а година довша."""

    async def since(self, key: str, since: datetime) -> list[datetime]:
        """Моменти подій за ключем не раніше `since`, від найстаріших."""
        ...

    async def record(self, key: str, at: datetime) -> None: ...

    async def purge(self, before: datetime) -> None:
        """Забуває події старші за `before` (для всіх ключів)."""
        ...


class SignupUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def signup_invites(self) -> SignupInviteRepository: ...

    @property
    def signup_requests(self) -> SignupRequestRepository: ...

    @property
    def signup_limits(self) -> SignupLimits: ...
