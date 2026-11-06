"""Листи-алерти LinkedIn → вакансії користувача. Викликає синк пошти у своїй транзакції (як
`match_replies`): кожен лист розбирається рівно один раз, вакансії без опису створюються у
стані «потрібен текст». Текст листа — недовірені дані."""

from dataclasses import dataclass, field
from datetime import datetime

from application.ports.ids import IdGenerator
from application.ports.mail import MailUnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.jobs.linkedin import ALERT_SOURCE, AlertJob, parse_job_alert
from domain.sources.dedup import DEDUP_WINDOW, RecentJob, find_same_job


@dataclass(slots=True)
class AlertReport:
    """Підсумок розбору нових алертів."""

    alerts: int = 0
    # Нові вакансії (стан «потрібен текст»).
    created: int = 0
    # Уже були в користувача (той самий лист у ресинку, той самий id з іншого алерту, ручне додавання).
    known: int = 0
    # Листи з позначкою помилки розбору (невідомий шаблон чи блоки, які не розібрались).
    failed: int = 0


@dataclass(slots=True)
class _Owner:
    """Власник листа й його недавні вакансії (поповнюються новими) для дедупу."""

    user_id: UserId
    recent: list[RecentJob] = field(default_factory=list)


async def import_alerts(
    uow: MailUnitOfWork, ids: IdGenerator, now: datetime
) -> AlertReport:
    """Нові листи linkedin_alert усіх користувачів (старіші першими) → вакансії власника листа.
    Лист із помилкою розбору теж позначається обробленим: вакансії, що розібрались, зберігаються,
    помилка лишається в `parse_error` листа, синк не падає."""
    report = AlertReport()
    owners: dict[UserId, _Owner] = {}
    for mail_id, user_id, text in await uow.mail_messages.pending_alerts():
        parsed = parse_job_alert(text)
        await uow.jobs.lock_additions(user_id)
        if user_id not in owners:
            since = now - DEDUP_WINDOW
            owners[user_id] = _Owner(user_id, await uow.jobs.recent(user_id, since))
        for alert in parsed.jobs:
            if await _save(uow, ids, now, owners[user_id], alert):
                report.created += 1
            else:
                report.known += 1
        await uow.mail_messages.mark_alerts_processed(mail_id, parsed.error, now)
        report.alerts += 1
        report.failed += bool(parsed.error)
    return report


async def _save(
    uow: MailUnitOfWork,
    ids: IdGenerator,
    now: datetime,
    owner: _Owner,
    alert: AlertJob,
) -> bool:
    """False — така вакансія в користувача вже є: той самий LinkedIn id (інший алерт, ручне
    додавання) або та сама «компанія + посада» за `DEDUP_WINDOW` під іншим id (LinkedIn дає
    одному оголошенню різні id)."""
    if await uow.jobs.find_linkedin(owner.user_id, alert.linkedin_id) is not None:
        return False
    if alert.company and find_same_job(owner.recent, alert.company, alert.title):
        return False
    job = NewJob(
        text=None,
        url=alert.url,
        title=alert.title,
        company=alert.company,
        linkedin_id=alert.linkedin_id,
        location=alert.location,
        source=ALERT_SOURCE,
    )
    number = await uow.jobs.add(owner.user_id, JobId(ids.new()), job, now)
    owner.recent.append(RecentJob(number, alert.company, alert.title, True))
    return True
