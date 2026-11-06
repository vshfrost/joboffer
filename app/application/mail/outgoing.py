"""Відправка листів застосунку з добовим лімітом. Ліміт рахується за журналом успішних
відправлень у базі (переживає перезапуск і однаковий для всіх процесів); понад ліміт запиту до
Google нема. Аудит — лише назва події: ні адреси, ні коду."""

from collections.abc import Callable
from dataclasses import dataclass
from string import Template

from application.ports.clock import Clock
from application.ports.outgoing_mail import MailAudit, MailSender, MailSendUnitOfWork
from application.ports.templates import TemplateKey, Templates
from domain.mail.outgoing import (
    MAIL_SEND_WINDOW,
    MailQuotaExceeded,
    MailUnavailable,
    OutgoingMail,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class OutgoingMailServices:
    sender: MailSender
    templates: Templates
    audit: MailAudit
    daily_limit: int


class OutgoingMailUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], MailSendUnitOfWork],
        clock: Clock,
        services: OutgoingMailServices,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._services = services

    async def send_signup_code(self, to: str, code: str) -> None:
        """Лист із кодом підтвердження. `MailQuotaExceeded` — ліміт вичерпано, `MailUnavailable` — збій."""
        templates = self._services.templates
        await self._send(
            OutgoingMail(
                to=to,
                subject=templates.get(TemplateKey.MAIL_SIGNUP_CODE_SUBJECT).strip(),
                body=Template(templates.get(TemplateKey.MAIL_SIGNUP_CODE)).substitute(
                    code=code
                ),
            )
        )

    async def send_account_exists(self, to: str) -> None:
        """Лист «акаунт уже є» (без коду) тому, хто реєструється на адресу наявного акаунта."""
        templates = self._services.templates
        await self._send(
            OutgoingMail(
                to=to,
                subject=templates.get(TemplateKey.MAIL_ACCOUNT_EXISTS_SUBJECT).strip(),
                body=templates.get(TemplateKey.MAIL_ACCOUNT_EXISTS),
            )
        )

    async def _send(self, mail: OutgoingMail) -> None:
        audit = self._services.audit
        async with self._unit_of_work() as uow:
            sent = await uow.mail_sends.count_since(
                self._clock.now() - MAIL_SEND_WINDOW
            )
        if sent >= self._services.daily_limit:
            audit.record("mail_quota_exceeded")
            raise MailQuotaExceeded("Добовий ліміт листів вичерпано.")
        try:
            await self._services.sender.send(mail)
        except MailUnavailable:
            audit.record("mail_unavailable")
            raise
        async with self._unit_of_work() as uow:
            await uow.mail_sends.record(self._clock.now())
            await uow.commit()
        audit.record("mail_sent")
