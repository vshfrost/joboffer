"""Фейки вихідної пошти для core-тестів: відправник, журнал відправлень, шаблони, аудит."""

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from application.ports.templates import TemplateKey
from domain.mail.outgoing import MailUnavailable, OutgoingMail

SUBJECT = "Код підтвердження joboffer"
BODY = "Ваш код підтвердження: $code\n\nЯкщо це були не ви, просто проігноруйте лист.\n"
EXISTS_SUBJECT = "Акаунт joboffer уже існує"
EXISTS_BODY = "На цю адресу вже є акаунт joboffer. Просто увійдіть зі своїм паролем.\n"


class FakeSender:
    def __init__(self, *, error: MailUnavailable | None = None) -> None:
        self.sent: list[OutgoingMail] = []
        self.error = error

    async def send(self, mail: OutgoingMail) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(mail)


class FakeTemplates:
    def get(self, key: TemplateKey) -> str:
        return {
            TemplateKey.MAIL_SIGNUP_CODE: BODY,
            TemplateKey.MAIL_SIGNUP_CODE_SUBJECT: SUBJECT + "\n",
            TemplateKey.MAIL_ACCOUNT_EXISTS: EXISTS_BODY,
            TemplateKey.MAIL_ACCOUNT_EXISTS_SUBJECT: EXISTS_SUBJECT + "\n",
        }[key]


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)


@dataclass(slots=True)
class SendStore:
    moments: list[datetime] = field(default_factory=list)


class InMemoryMailSends:
    def __init__(self, store: SendStore) -> None:
        self._store = store

    async def count_since(self, moment: datetime) -> int:
        return sum(1 for sent in self._store.moments if sent > moment)

    async def record(self, sent_at: datetime) -> None:
        self._store.moments.append(sent_at)


class InMemorySendUnitOfWork:
    """Зміни видно лише після `commit()`."""

    def __init__(self, store: SendStore) -> None:
        self._store = store
        self._staged: SendStore | None = None

    async def __aenter__(self) -> Self:
        self._staged = SendStore(list(self._store.moments))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._staged = None

    async def commit(self) -> None:
        assert self._staged is not None
        self._store.moments[:] = self._staged.moments

    @property
    def mail_sends(self) -> InMemoryMailSends:
        assert self._staged is not None
        return InMemoryMailSends(self._staged)
