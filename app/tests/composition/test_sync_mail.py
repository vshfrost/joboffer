"""Запуск синку пошти: креди Gmail лише з оточення, без них синк не стартує; код виходу й
аудит без вмісту листів."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.mail.sync import MailSyncUseCases
from bootstrap import sync_mail
from bootstrap.settings import Settings
from domain.mail.mail import IncomingMail, MailboxError, personal_address
from tests.support import linkedin_alerts
from tests.support.clock import FakeClock
from tests.support.core_conftest import portal
from tests.support.ids import SequentialIds
from tests.support.mail import (
    FakeMailbox,
    InMemoryMailUnitOfWork,
    MailStore,
    auth_headers,
    user,
)

__all__ = ["portal"]

DUMMY_URL = "postgresql+psycopg://joboffer@localhost:1/joboffer"
GMAIL_ENV = (
    "JOBOFFER_GMAIL_CLIENT_ID",
    "JOBOFFER_GMAIL_CLIENT_SECRET",
    "JOBOFFER_GMAIL_REFRESH_TOKEN",
)
MAILBOX = "mailroom@example.com"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", DUMMY_URL)
    for name in ("JOBOFFER_MAIL_ADDRESS", *GMAIL_ENV):
        monkeypatch.delenv(name, raising=False)


def test_app_and_agent_settings_have_no_gmail_credentials() -> None:
    settings = Settings()

    assert settings.mail_address == ""
    assert settings.gmail_client_id is None
    assert settings.gmail_client_secret is None
    assert settings.gmail_refresh_token is None


def test_blank_gmail_values_from_compose_mean_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in GMAIL_ENV:
        monkeypatch.setenv(name, "")

    settings = Settings()

    assert settings.gmail_client_id is None
    assert settings.gmail_client_secret is None
    assert settings.gmail_refresh_token is None


def test_gmail_credentials_come_from_environment_and_stay_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOBOFFER_MAIL_ADDRESS", "mailroom@example.com")
    for name, value in zip(GMAIL_ENV, ("id", "secret-x", "refresh-x"), strict=True):
        monkeypatch.setenv(name, value)

    settings = Settings()

    assert settings.mail_address == "mailroom@example.com"
    assert settings.gmail_client_id == "id"
    assert settings.gmail_client_secret is not None
    assert settings.gmail_client_secret.get_secret_value() == "secret-x"
    assert settings.gmail_refresh_token is not None
    assert settings.gmail_refresh_token.get_secret_value() == "refresh-x"
    assert "secret-x" not in repr(settings)
    assert "refresh-x" not in repr(settings)


@pytest.mark.parametrize("missing", ["JOBOFFER_MAIL_ADDRESS", *GMAIL_ENV])
def test_sync_refuses_to_start_without_mailbox_or_credentials(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for name in ("JOBOFFER_MAIL_ADDRESS", *GMAIL_ENV):
        if name != missing:
            monkeypatch.setenv(name, "x")

    with pytest.raises(SystemExit, match="JOBOFFER_MAIL_ADDRESS"):
        sync_mail.main()


@pytest.fixture
def audit_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> pytest.LogCaptureFixture:
    """Аудит-логер доступний для caplog: попередні тести (import-linter) налаштовують logging
    через dictConfig і вимикають вже створені логери."""
    for name in ("joboffer", "joboffer.mail"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "disabled", False)
        monkeypatch.setattr(logger, "propagate", True)
    caplog.set_level(logging.INFO, logger="joboffer.mail")
    return caplog


class Run:
    def __init__(self, portal: BlockingPortal) -> None:
        self.portal = portal
        self.store = MailStore()
        self.use_cases = MailSyncUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), FakeClock(NOW), SequentialIds()
        )

    def address(self) -> str:
        async def ensure() -> str:
            async with InMemoryMailUnitOfWork(self.store) as uow:
                inbox = await uow.mail_inboxes.ensure(user(1))
                await uow.commit()
            return personal_address(MAILBOX, inbox.tag)

        return self.portal.call(ensure)

    def run(self, box: FakeMailbox) -> int:
        return self.portal.call(sync_mail.run_sync, self.use_cases, box, MAILBOX)


def letter(gmail_id: str, to: str) -> IncomingMail:
    return IncomingMail(
        id=gmail_id,
        received_at=NOW - timedelta(hours=1),
        from_address="talent@acme.example",
        auth_headers=auth_headers("talent@acme.example"),
        delivered_to=(to,),
        subject="Subject with secret-subject",
        text="Body with secret-body",
    )


def test_run_syncs_and_writes_audit_lines_without_content(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    box = FakeMailbox()
    box.deliver(letter("a1", run.address()), letter("x1", "mailroom@example.com"))

    code = run.run(box)

    assert code == 0
    assert set(run.store.messages) == {"a1"}
    assert "MAIL_AUDIT dropped gmail_id=x1 reason=no_tag" in audit_log.text
    assert "MAIL_AUDIT sync done: stored=1 known=0 gone=0 dropped=1" in audit_log.text
    assert "secret-body" not in audit_log.text
    assert "secret-subject" not in audit_log.text
    assert "talent@acme.example" not in audit_log.text


def test_run_audits_alert_counts_without_vacancy_content(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    box = FakeMailbox()
    alert = IncomingMail(
        id="al1",
        received_at=NOW - timedelta(hours=1),
        from_address="jobalerts-noreply@linkedin.com",
        auth_headers=auth_headers("jobalerts-noreply@linkedin.com"),
        delivered_to=(run.address(),),
        subject="Нові вакансії",
        text=linkedin_alerts.SPAIN,
    )
    box.deliver(alert)

    code = run.run(box)

    assert code == 0
    assert "MAIL_AUDIT alerts: alerts=1 created=6 known=0 failed=0" in audit_log.text
    assert "Affirm" not in audit_log.text
    assert "Senior Python Developer" not in audit_log.text


def test_run_exits_with_error_and_records_it_without_secrets(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    box = FakeMailbox(error=MailboxError("Gmail відповів 500 на profile."))

    code = run.run(box)

    assert code == 1
    assert run.store.sync[MAILBOX].last_error == "Gmail відповів 500 на profile."
    assert "MAIL_AUDIT sync failed: Gmail відповів 500 на profile." in audit_log.text


def test_run_skips_while_another_sync_runs(
    portal: BlockingPortal, audit_log: pytest.LogCaptureFixture
) -> None:
    run = Run(portal)
    run.store.sync_busy = True
    box = FakeMailbox()

    code = run.run(box)

    assert code == 0
    assert "MAIL_AUDIT sync skipped" in audit_log.text
    assert box.since_calls == []


class ClosableMailbox(FakeMailbox):
    closed = False

    async def aclose(self) -> None:
        self.closed = True


class FakeEngine:
    disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def main_env(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ClosableMailbox, FakeEngine, MailStore]:
    """`main()` без мережі й бази: скринька, engine і сховище підмінені на фейки."""
    box, engine, store = ClosableMailbox(), FakeEngine(), MailStore()
    monkeypatch.setenv("JOBOFFER_MAIL_ADDRESS", MAILBOX)
    for name in GMAIL_ENV:
        monkeypatch.setenv(name, "x")
    monkeypatch.setattr(sync_mail, "connect", lambda creds: box)
    monkeypatch.setattr(sync_mail, "create_engine", lambda url: engine)
    monkeypatch.setattr(
        sync_mail,
        "unit_of_work_factory",
        lambda _engine: lambda: InMemoryMailUnitOfWork(store),
    )
    return box, engine, store


def test_main_syncs_and_releases_the_mailbox_and_the_engine(
    main_env: tuple[ClosableMailbox, FakeEngine, MailStore],
) -> None:
    box, engine, store = main_env

    sync_mail.main()

    assert store.sync[MAILBOX].history_id == str(box.cursor)
    assert box.closed
    assert engine.disposed


def test_main_exits_with_code_1_when_the_mailbox_fails(
    main_env: tuple[ClosableMailbox, FakeEngine, MailStore],
) -> None:
    box, engine, store = main_env
    box.error = MailboxError("Gmail відповів 500 на profile.")

    with pytest.raises(SystemExit) as exit_info:
        sync_mail.main()

    assert exit_info.value.code == 1
    assert store.sync[MAILBOX].last_error == "Gmail відповів 500 на profile."
    assert box.closed
    assert engine.disposed
