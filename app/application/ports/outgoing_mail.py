"""Порти вихідної пошти: відправник (Gmail), журнал відправлень для ліміту й аудит."""

from datetime import datetime
from typing import Protocol

from application.ports.unit_of_work import UnitOfWork
from domain.mail.outgoing import OutgoingMail


class MailSender(Protocol):
    async def send(self, mail: OutgoingMail) -> None:
        """Відправляє лист. Збій — `MailUnavailable`."""
        ...


class MailSends(Protocol):
    """Журнал успішних відправлень: лише моменти, без адрес і текстів."""

    async def count_since(self, moment: datetime) -> int: ...

    async def record(self, sent_at: datetime) -> None: ...


class MailSendUnitOfWork(UnitOfWork, Protocol):
    @property
    def mail_sends(self) -> MailSends: ...


class MailAudit(Protocol):
    def record(self, event: str) -> None:
        """Подія відправки за назвою: без адрес і кодів."""
        ...
