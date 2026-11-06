"""Use cases реєстрації: signup → verify → resend.

Користувач з'являється в `users` лише після правильного коду з листа; до того дані чекають
у запиті на реєстрацію (лише хеш пароля й digest коду).
"""

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from application.contracts.invites import CheckInvite
from application.contracts.legal import LegalDoc
from application.contracts.sessions import SessionIssued
from application.contracts.signup import Signup, SignupAccepted, VerifySignup
from application.identity.altcha import AltchaUseCases
from application.identity.invites import SignupInviteUseCases
from application.identity.limits import Limit, ensure_below
from application.identity.sessions import SessionUseCases
from application.identity.use_cases import display_name_for, user_view
from application.mail.outgoing import OutgoingMailUseCases
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.legal import LegalDocuments
from application.ports.passwords import PasswordHasher
from application.ports.signup import CodeGenerator, SignupUnitOfWork
from domain.identity.email import Email
from domain.identity.errors import (
    CodeIncorrect,
    InviteAlreadyUsed,
    RegistrationClosed,
    SignupClosed,
    SignupExpired,
    SignupMailUnavailable,
    TooManyAttempts,
)
from domain.identity.ids import SignupRequestId, UserId
from domain.identity.password_policy import check_new_password
from domain.identity.session import TokenDigest
from domain.identity.signup import SignupMode
from domain.identity.signup_request import (
    MAIL_MAX_PER_WINDOW,
    MAIL_WINDOW,
    SIGNUP_MAX_PER_WINDOW,
    SIGNUP_WINDOW,
    SignupDraft,
    SignupRequest,
)
from domain.identity.throttle import signup_client_key, signup_mail_key
from domain.identity.user import User
from domain.mail.outgoing import MailQuotaExceeded, MailUnavailable
from domain.shared.errors import InvalidValue

EXPIRED_MESSAGE = "Запит на реєстрацію недійсний або прострочений. Почни спочатку"
MAIL_FAILED_MESSAGE = "Не вдалося надіслати лист. Спробуй пізніше"
CLIENT_LIMIT = Limit(
    SIGNUP_WINDOW, SIGNUP_MAX_PER_WINDOW, "Забагато реєстрацій. Спробуй пізніше"
)
MAIL_LIMIT = Limit(
    MAIL_WINDOW, MAIL_MAX_PER_WINDOW, "Забагато листів на цю адресу. Спробуй пізніше"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupServices:
    """Залежності реєстрації, що не стосуються сховища."""

    clock: Clock
    ids: IdGenerator
    hasher: PasswordHasher
    codes: CodeGenerator
    altcha: AltchaUseCases
    invites: SignupInviteUseCases
    legal: LegalDocuments
    sessions: SessionUseCases
    # None — пошту не налаштовано: реєстрація закрита.
    mail: OutgoingMailUseCases | None
    mode: SignupMode


class SignupUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], SignupUnitOfWork],
        services: SignupServices,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._services = services

    async def signup(self, command: Signup) -> SignupAccepted:
        """Приймає дані й надсилає код (або лист «акаунт уже є»); користувача ще не створює.

        Відповідь однакова для нового й наявного email, щоб форма не розкривала, хто зареєстрований.
        """
        services = self._services
        self._ensure_open()
        if command.website:
            # Приманка для ботів: людина її не бачить. Відповідаємо як успіхом, але нічого не робимо.
            return SignupAccepted(signup_id=str(services.ids.new()))
        mail = self._mail()
        await services.altcha.verify(command.altcha)
        await services.invites.check(
            CheckInvite(token=command.invite, client=command.client)
        )
        if command.terms_version != services.legal.get(LegalDoc.TERMS).version:
            raise InvalidValue(
                "terms_version", "Потрібна згода з поточною версією умов"
            )
        email = Email.parse(command.email)
        display_name = display_name_for(command.display_name, email)
        check_new_password(command.password)
        draft = SignupDraft(
            email=email,
            # Хешуємо й для наявного email: час відповіді не розкриває, чи він зайнятий.
            password_hash=await services.hasher.hash(command.password),
            display_name=display_name,
            invite_digest=TokenDigest.from_token(command.invite),
            terms_version=command.terms_version,
        )
        now = services.clock.now()
        client_key, mail_key = (
            signup_client_key(command.client),
            signup_mail_key(email.value),
        )
        signup_id = SignupRequestId(services.ids.new())
        async with self._unit_of_work() as uow:
            await uow.signup_requests.purge_expired(now)
            await uow.signup_limits.purge(now - max(SIGNUP_WINDOW, MAIL_WINDOW))
            await ensure_below(uow.signup_limits, client_key, CLIENT_LIMIT, now)
            await ensure_below(uow.signup_limits, mail_key, MAIL_LIMIT, now)
            if await uow.users.find_by_email(email) is not None:
                await self._deliver(mail.send_account_exists(email.value))
            else:
                code = services.codes.new()
                await uow.signup_requests.add(
                    SignupRequest.issue(draft, id=signup_id, code=code, now=now)
                )
                await self._deliver(mail.send_signup_code(email.value, code))
            await uow.signup_limits.record(client_key, now)
            await uow.signup_limits.record(mail_key, now)
            await uow.commit()
        return SignupAccepted(signup_id=str(signup_id.value))

    async def verify(self, command: VerifySignup) -> SessionIssued:
        """Правильний код → користувач, згода, погашене запрошення й сесія в одній транзакції."""
        self._ensure_open()
        request_id = _parse_id(command.signup_id)
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            request = await uow.signup_requests.get(request_id)
            if request is None:
                raise SignupExpired(EXPIRED_MESSAGE)
            if request.is_expired(now):
                await uow.signup_requests.delete(request.id)
                await uow.commit()
                raise SignupExpired(EXPIRED_MESSAGE)
            if not request.matches(command.code):
                failed = request.failed()
                if failed.attempts_left == 0:
                    await uow.signup_requests.delete(request.id)
                    await uow.commit()
                    raise SignupExpired(EXPIRED_MESSAGE)
                await uow.signup_requests.save(failed)
                await uow.commit()
                raise CodeIncorrect(
                    f"Невірний код. Залишилось спроб: {failed.attempts_left}",
                    attempts_left=failed.attempts_left,
                )
            if not await uow.signup_invites.redeem(request.invite_digest, now):
                raise InviteAlreadyUsed("Запрошення вже використано")
            user = User.register(
                id=UserId(self._services.ids.new()),
                email=request.email,
                display_name=request.display_name,
                password_hash=request.password_hash,
                now=now,
            ).accepting_terms(request.terms_version, request.created_at)
            await uow.users.add(
                user
            )  # email зайняли, поки чекали код: EmailTaken, погашення відкотиться
            await uow.signup_requests.delete(request.id)
            await uow.commit()
        return await self._services.sessions.open_session(user_view(user))

    async def resend(self, signup_id: str) -> SignupAccepted:
        """Новий код на ту саму адресу: не раніше ніж через 60 секунд і не більше 5 листів на годину."""
        self._ensure_open()
        mail = self._mail()
        request_id = _parse_id(signup_id)
        now = self._services.clock.now()
        async with self._unit_of_work() as uow:
            request = await uow.signup_requests.get(request_id)
            if request is None:
                raise SignupExpired(EXPIRED_MESSAGE)
            if request.is_expired(now):
                await uow.signup_requests.delete(request.id)
                await uow.commit()
                raise SignupExpired(EXPIRED_MESSAGE)
            wait = request.resend_wait(now)
            if wait > timedelta(0):
                raise TooManyAttempts(
                    "Новий код можна запросити трохи пізніше",
                    retry_after=math.ceil(wait.total_seconds()),
                )
            mail_key = signup_mail_key(request.email.value)
            await ensure_below(uow.signup_limits, mail_key, MAIL_LIMIT, now)
            code = self._services.codes.new()
            await uow.signup_requests.save(request.with_new_code(code, now))
            await self._deliver(mail.send_signup_code(request.email.value, code))
            await uow.signup_limits.record(mail_key, now)
            await uow.commit()
        return SignupAccepted(signup_id=signup_id)

    def _ensure_open(self) -> None:
        if self._services.mode is SignupMode.CLOSED:
            raise SignupClosed("Реєстрація закрита")

    def _mail(self) -> OutgoingMailUseCases:
        if self._services.mail is None:
            raise RegistrationClosed("Реєстрація закрита")
        return self._services.mail

    async def _deliver(self, sending: Awaitable[None]) -> None:
        """Збій пошти чи вичерпаний ліміт листів — `SignupMailUnavailable`; транзакція відкотиться."""
        try:
            await sending
        except MailUnavailable, MailQuotaExceeded:
            raise SignupMailUnavailable(MAIL_FAILED_MESSAGE) from None


def _parse_id(raw: str) -> SignupRequestId:
    """Недійсний id — те саме `SignupExpired`, що й невідомий: відповідь не розкриває різниці."""
    try:
        return SignupRequestId.parse(raw)
    except InvalidValue:
        raise SignupExpired(EXPIRED_MESSAGE) from None
