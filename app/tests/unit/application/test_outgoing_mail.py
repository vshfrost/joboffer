"""Відправка листів застосунку: шаблони, добовий ліміт, аудит без адреси й коду."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.mail.outgoing import OutgoingMailServices, OutgoingMailUseCases
from domain.mail.outgoing import (
    MAIL_SEND_DAILY_LIMIT,
    MailQuotaExceeded,
    MailUnavailable,
    OutgoingMail,
)
from tests.support.clock import FakeClock
from tests.support.outgoing import (
    EXISTS_BODY,
    EXISTS_SUBJECT,
    SUBJECT,
    FakeAudit,
    FakeSender,
    FakeTemplates,
    InMemorySendUnitOfWork,
    SendStore,
)

ADDRESS = "candidate@example.com"
CODE = "483920"


class Setup:
    def __init__(
        self,
        portal: BlockingPortal,
        *,
        limit: int = 3,
        error: MailUnavailable | None = None,
    ) -> None:
        self.portal = portal
        self.store = SendStore()
        self.clock = FakeClock()
        self.sender = FakeSender(error=error)
        self.audit = FakeAudit()
        self.use_cases = OutgoingMailUseCases(
            lambda: InMemorySendUnitOfWork(self.store),
            self.clock,
            OutgoingMailServices(
                sender=self.sender,
                templates=FakeTemplates(),
                audit=self.audit,
                daily_limit=limit,
            ),
        )

    def send(self) -> None:
        self.portal.call(self.use_cases.send_signup_code, ADDRESS, CODE)


def test_the_default_daily_limit_is_50() -> None:
    assert MAIL_SEND_DAILY_LIMIT == 50


def test_signup_code_mail_goes_to_the_address_with_the_code_in_the_body(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal)

    setup.send()

    assert setup.sender.sent == [
        OutgoingMail(
            to=ADDRESS,
            subject=SUBJECT,
            body="Ваш код підтвердження: 483920\n\nЯкщо це були не ви, просто проігноруйте лист.\n",
        )
    ]


def test_the_limit_of_mails_per_day_is_allowed(portal: BlockingPortal) -> None:
    setup = Setup(portal, limit=3)

    for _ in range(3):
        setup.send()

    assert len(setup.sender.sent) == 3


def test_the_mail_over_the_daily_limit_is_refused_and_never_sent(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal, limit=3)
    for _ in range(3):
        setup.send()

    with pytest.raises(MailQuotaExceeded):
        setup.send()

    assert len(setup.sender.sent) == 3


def test_mails_older_than_24_hours_do_not_count(portal: BlockingPortal) -> None:
    setup = Setup(portal, limit=3)
    for _ in range(3):
        setup.send()

    setup.clock.advance(timedelta(hours=24, seconds=1))
    setup.send()

    assert len(setup.sender.sent) == 4


def test_a_mail_just_inside_the_24_hour_window_still_counts(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal, limit=1)
    setup.send()

    setup.clock.advance(timedelta(hours=23, minutes=59))

    with pytest.raises(MailQuotaExceeded):
        setup.send()


def test_a_failed_send_raises_unavailable_and_does_not_use_the_quota(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal, limit=1, error=MailUnavailable("Gmail відповів 500."))

    with pytest.raises(MailUnavailable):
        setup.send()
    setup.sender.error = None
    setup.send()

    assert len(setup.sender.sent) == 1


def test_audit_names_the_outcome_without_the_address_or_the_code(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal, limit=1)
    setup.send()
    with pytest.raises(MailQuotaExceeded):
        setup.send()
    setup.clock.advance(timedelta(hours=25))
    setup.sender.error = MailUnavailable("Gmail відповів 500.")
    with pytest.raises(MailUnavailable):
        setup.send()

    assert setup.audit.events == [
        "mail_sent",
        "mail_quota_exceeded",
        "mail_unavailable",
    ]
    assert ADDRESS not in "".join(setup.audit.events)
    assert CODE not in "".join(setup.audit.events)


def test_account_exists_mail_goes_to_the_address_without_any_code(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal)

    portal.call(setup.use_cases.send_account_exists, ADDRESS)

    assert setup.sender.sent == [
        OutgoingMail(to=ADDRESS, subject=EXISTS_SUBJECT, body=EXISTS_BODY)
    ]


def test_account_exists_mail_counts_toward_the_daily_limit(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal, limit=1)
    portal.call(setup.use_cases.send_account_exists, ADDRESS)

    with pytest.raises(MailQuotaExceeded):
        portal.call(setup.use_cases.send_account_exists, ADDRESS)

    assert len(setup.sender.sent) == 1


def test_account_exists_audit_has_neither_the_address_nor_a_code(
    portal: BlockingPortal,
) -> None:
    setup = Setup(portal)

    portal.call(setup.use_cases.send_account_exists, ADDRESS)

    assert setup.audit.events == ["mail_sent"]
