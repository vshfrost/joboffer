"""Агрегат User: незмінний; реєстрація повертає користувача з version=1 і подією.

Час і ID приходять явними значеннями — домен не викликає now() чи uuid4().
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Self

from domain.identity.email import Email
from domain.identity.events import UserRegisteredEvent
from domain.identity.ids import UserId
from domain.identity.password import PasswordHash
from domain.shared.errors import InvalidValue

DISPLAY_NAME_MAX = 100


@dataclass(frozen=True, slots=True)
class DisplayName:
    """1..100 символів без пробілів на краях. `parse` прибирає їх; конструктор лише перевіряє."""

    value: str

    def __post_init__(self) -> None:
        if self.value != self.value.strip():
            raise InvalidValue("display_name", "Імʼя без пробілів на початку й у кінці")
        if not 1 <= len(self.value) <= DISPLAY_NAME_MAX:
            raise InvalidValue(
                "display_name", f"Імʼя — від 1 до {DISPLAY_NAME_MAX} символів"
            )

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw.strip())


@dataclass(frozen=True, slots=True, kw_only=True)
class User:
    id: UserId
    email: Email
    display_name: DisplayName
    # Користувач, створений входом через Google, пароля не має.
    password_hash: PasswordHash | None
    version: int
    created_at: datetime
    # Згода з умовами при реєстрації: версія тексту й момент; None — користувач до появи згоди.
    terms_version: str | None = None
    terms_accepted_at: datetime | None = None
    # Нові події з моменту завантаження; не впливають на рівність. Їх забирає use case.
    events: tuple[UserRegisteredEvent, ...] = field(
        default=(), compare=False, repr=False
    )

    @classmethod
    def register(
        cls,
        *,
        id: UserId,
        email: Email,
        display_name: DisplayName,
        password_hash: PasswordHash | None,
        now: datetime,
    ) -> Self:
        return cls(
            id=id,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            version=1,
            created_at=now,
            events=(UserRegisteredEvent(user_id=id, version=1),),
        )

    def accepting_terms(self, version: str, at: datetime) -> Self:
        """Користувач, що погодився з умовами цієї версії в момент `at`."""
        return replace(self, terms_version=version, terms_accepted_at=at)
