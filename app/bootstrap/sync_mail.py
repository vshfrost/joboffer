"""Синк пошти: нові листи скриньки застосунку → листи користувачів. Одноразовий запуск —
`python -m bootstrap.sync_mail` (сервіс mailsync у compose; на сервері — таймер, B12). Креди
Gmail є лише в оточенні цього процесу. Аудит — рядки MAIL_AUDIT без вмісту листів."""

import asyncio
import logging

from application.mail.sync import MailSyncUseCases
from application.ports.mail import Mailbox
from bootstrap.settings import Settings
from domain.mail.mail import MailboxError
from infrastructure.db.engine import create_engine
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.gmail.client import GmailCredentials, connect
from infrastructure.system import RandomIds, SystemClock

logger = logging.getLogger("joboffer.mail")


async def run_sync(use_cases: MailSyncUseCases, mailbox: Mailbox, address: str) -> int:
    """Один прохід синку; код виходу процесу: 0 — пройшов або пропущений (синк уже йде),
    1 — скринька недоступна (помилка вже записана в стан синку)."""
    try:
        report = await use_cases.sync_mail(mailbox, address)
    except MailboxError as exc:
        logger.error("MAIL_AUDIT sync failed: %s", exc)  # noqa: TRY400 — без трейсбеку: він міг би нести секрети
        return 1
    if report.locked:
        logger.info("MAIL_AUDIT sync skipped: інший синк ще працює")
        return 0
    for dropped in report.dropped:
        logger.info(
            "MAIL_AUDIT dropped gmail_id=%s reason=%s", dropped.gmail_id, dropped.reason
        )
    logger.info(
        "MAIL_AUDIT sync done: stored=%d known=%d gone=%d dropped=%d resynced=%s",
        report.stored,
        report.known,
        report.gone,
        len(report.dropped),
        report.resynced,
    )
    logger.info(
        "MAIL_AUDIT alerts: alerts=%d created=%d known=%d failed=%d",
        report.alerts.alerts,
        report.alerts.created,
        report.alerts.known,
        report.alerts.failed,
    )
    return 0


async def _run(settings: Settings, creds: GmailCredentials) -> int:
    engine = create_engine(settings.database_url.get_secret_value())
    mailbox = connect(creds)
    try:
        use_cases = MailSyncUseCases(
            unit_of_work_factory(engine), SystemClock(), RandomIds()
        )
        return await run_sync(use_cases, mailbox, settings.mail_address)
    finally:
        await mailbox.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    settings = Settings()
    secret, refresh = settings.gmail_client_secret, settings.gmail_refresh_token
    if not (settings.mail_address and settings.gmail_client_id and secret and refresh):
        raise SystemExit(
            "Синк пошти потребує JOBOFFER_MAIL_ADDRESS і JOBOFFER_GMAIL_CLIENT_ID / "
            "_CLIENT_SECRET / _REFRESH_TOKEN (значення задає Богдан в infra/.env)."
        )
    creds = GmailCredentials(
        client_id=settings.gmail_client_id,
        client_secret=secret.get_secret_value(),
        refresh_token=refresh.get_secret_value(),
    )
    code = asyncio.run(_run(settings, creds))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
