"""Use cases identity. REST, MCP чи CLI викликають саме їх — правила входу й реєстрації в одному місці.

Хешування паролів — дорога операція, тож вона йде поза транзакцією: UoW відкривається лише
для читання чи запису користувача.
"""

from collections.abc import Callable

from application.contracts.identity import (
    Authenticate,
    CreateUser,
    GoogleClaims,
    UserView,
)
from application.ports.clock import Clock
from application.ports.identity import IdentityUnitOfWork
from application.ports.ids import IdGenerator
from application.ports.passwords import PasswordHasher
from domain.identity.email import Email
from domain.identity.errors import (
    INVALID_CREDENTIALS_MESSAGE,
    EmailRequired,
    InvalidCredentials,
)
from domain.identity.external_identity import GOOGLE, ExternalIdentity
from domain.identity.ids import ExternalIdentityId, UserId
from domain.identity.password_policy import PASSWORD_MAX
from domain.identity.user import DISPLAY_NAME_MAX, DisplayName, User
from domain.shared.errors import InvalidValue

# Пароль, який оператор задає через CLI `create_user`; політика реєстрації (8+ і класи) окрема.
PASSWORD_MIN = 12


def user_view(user: User) -> UserView:
    return UserView(
        id=str(user.id),
        email=user.email.value,
        display_name=user.display_name.value,
        created_at=user.created_at,
    )


def _verified_email(claims: GoogleClaims) -> Email:
    if not claims.email_verified or not claims.email:
        raise EmailRequired("Google не передав підтверджений email")
    try:
        return Email.parse(claims.email)
    except InvalidValue as error:
        raise EmailRequired("Google передав некоректний email") from error


def display_name_for(name: str | None, email: Email) -> DisplayName:
    """Вказане імʼя (Google чи форма реєстрації); без нього — частина email до `@`. Обрізається до ліміту."""
    candidate = (name or "").strip() or email.value.partition("@")[0]
    return DisplayName.parse(candidate[:DISPLAY_NAME_MAX])


class IdentityUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], IdentityUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        hasher: PasswordHasher,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._hasher = hasher

    async def create_user(self, command: CreateUser) -> UserView:
        email = Email.parse(command.email)
        display_name = DisplayName.parse(command.display_name)
        if not PASSWORD_MIN <= len(command.password) <= PASSWORD_MAX:
            raise InvalidValue(
                "password", f"Пароль — від {PASSWORD_MIN} до {PASSWORD_MAX} символів"
            )
        user = User.register(
            id=UserId(self._ids.new()),
            email=email,
            display_name=display_name,
            password_hash=await self._hasher.hash(command.password),
            now=self._clock.now(),
        )
        async with self._unit_of_work() as uow:
            await uow.users.add(user)  # унікальність email гарантує сховище
            await uow.commit()
        return user_view(user)

    async def sign_in_with_google(self, claims: GoogleClaims) -> UserView:
        """Лише наявний користувач: за Google `sub` → за email (привʼязує identity). Нового Google не створює.

        Без підтвердженого email чи з email, якого нема в `users`, — `EmailRequired`. Підтверджений email потрібен
        і відомому `sub`: його втрата означає, що провайдер більше не ручається за адресу.
        """
        email = _verified_email(claims)
        async with self._unit_of_work() as uow:
            known = await uow.external_identities.find(GOOGLE, claims.subject)
            if known is not None:
                return user_view(await uow.users.get(known.user_id))
            user = await uow.users.find_by_email(email)
            if user is None:
                raise EmailRequired("Google-вхід лише для наявних користувачів")
            await uow.external_identities.add(
                ExternalIdentity(
                    id=ExternalIdentityId(self._ids.new()),
                    provider=GOOGLE,
                    subject=claims.subject,
                    user_id=user.id,
                    created_at=self._clock.now(),
                )
            )
            await uow.commit()
        return user_view(user)

    async def authenticate(self, command: Authenticate) -> UserView:
        """Будь-яка причина невдачі — одна й та сама `InvalidCredentials`.

        Пароль перевіряється й для невідомого email (`stored=None`), щоб час відповіді не
        розкривав, чи такий користувач є. Надмірно довгий пароль відхиляється без хешування.
        """
        if len(command.password) > PASSWORD_MAX:
            raise InvalidCredentials(INVALID_CREDENTIALS_MESSAGE)
        user = await self._find(command.email)
        matched = await self._hasher.verify(
            command.password, user.password_hash if user else None
        )
        if user is None or not matched:
            raise InvalidCredentials(INVALID_CREDENTIALS_MESSAGE)
        return user_view(user)

    async def _find(self, raw_email: str) -> User | None:
        try:
            email = Email.parse(raw_email)
        except InvalidValue:
            return None
        async with self._unit_of_work() as uow:
            return await uow.users.find_by_email(email)
