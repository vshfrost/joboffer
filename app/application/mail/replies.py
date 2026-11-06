"""Відповіді на подачі: синк зіставляє нові листи компаній з поданими вакансіями власника
листа, користувач з агентом підтверджує тип і вакансію, статус подачі рухається вперед.
Текст листів — недовірені дані; чужих відповідей тут не видно."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from application.applications.use_cases import application_data
from application.contracts.actor import Actor
from application.contracts.replies import (
    ReplyDetailData,
    ReviewedReplyData,
    ReviewInput,
)
from application.ports.clock import Clock
from application.ports.mail import MailUnitOfWork
from domain.applications.application import TRANSITIONS, Application
from domain.identity.ids import UserId
from domain.mail.board import ReplyBoard, ReplyQuery, ReviewEffect, review_effect
from domain.mail.forwarded import manual_forward
from domain.mail.inbox import display_text
from domain.mail.replies import (
    DEFAULT_REPLIES_LIMIT,
    AppliedJob,
    Reply,
    auto_status,
    check_replies_limit,
    match_reply,
    parse_reply_type,
    review_target,
    suggest_type,
)
from domain.shared.errors import NotFound


@dataclass(slots=True)
class MatchReport:
    matched: int = 0
    unmatched: int = 0
    # Подачі, що самі перейшли applied → replied.
    replied: int = 0


async def match_replies(uow: MailUnitOfWork, now: datetime) -> MatchReport:
    """Листи компаній без зіставлення (усіх користувачів, старші першими) → зіставлення з
    подачами власника листа. Викликає синк пошти у своїй транзакції; старші листи йдуть
    першими, тож відповідь у треді бачить уже зіставлений попередній лист."""
    report = MatchReport()
    applied: dict[UserId, list[AppliedJob]] = {}
    emails: dict[UserId, str] = {}
    for user_id, mail in await uow.job_replies.pending():
        if user_id not in applied:
            applied[user_id] = await uow.job_replies.applied(user_id)
            emails[user_id] = await owner_email(uow, user_id)
        jobs = applied[user_id]
        thread_job = await uow.job_replies.thread_job(user_id, mail.thread_ids)
        # Ручне пересилання: відправник і тема — з блоку пересланого листа; його відправник
        # не перевірений, тож статус подачі за таким листом сам не змінюється.
        forwarded = manual_forward(
            emails[user_id], mail.from_address, mail.sender_auth, mail.text
        )
        seen = (
            mail
            if forwarded is None
            else replace(
                mail,
                from_address=forwarded.from_address,
                from_name=forwarded.from_name,
                subject=forwarded.subject,
            )
        )
        match = match_reply(seen, jobs, thread_job)
        suggested = suggest_type(seen.subject, seen.text)
        await uow.job_replies.add(user_id, mail.id, match, suggested)
        if match.job_number is None:
            report.unmatched += 1
            continue
        report.matched += 1
        job = next(job for job in jobs if job.job_number == match.job_number)
        status = (
            None
            if forwarded is not None
            else auto_status(match, suggested, mail.sender_auth)
        )
        if status is not None and status in TRANSITIONS[job.status]:
            await uow.applications.set_status(user_id, job.job_number, status, now)
            applied[user_id] = [
                replace(item, status=status) if item is job else item for item in jobs
            ]
            report.replied += 1
    return report


class ReplyUseCases:
    def __init__(
        self, unit_of_work: Callable[[], MailUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def list_replies(
        self,
        actor: Actor,
        *,
        reviewed: bool = False,
        limit: int = DEFAULT_REPLIES_LIMIT,
    ) -> list[Reply]:
        """Відповіді користувача: нерозібрані (або розібрані), новіші першими. `InvalidValue`
        (поле `limit`) — поза межами 1..50."""
        check_replies_limit(limit)
        async with self._unit_of_work() as uow:
            found = await uow.job_replies.list(
                actor.user_id, reviewed=reviewed, limit=limit
            )
            return _marked(found, await owner_email(uow, actor.user_id))

    async def review_reply(self, actor: Actor, data: ReviewInput) -> ReviewedReplyData:
        """Підтверджує тип і вакансію відповіді (`job_number` None — лист не про подачу) і веде
        подачу вперед за типом; назад статус не рухається. Повторний розбір замінює
        попередній. `InvalidValue` — невідомий тип; `NotFound` — відповіді чи подачі нема."""
        kind = parse_reply_type(data.type)
        user_id, job_number = actor.user_id, data.job_number
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            if await uow.job_replies.get(user_id, data.reply_id) is None:
                raise NotFound(f"Відповідь {data.reply_id} не знайдено.")
            application = None
            if job_number is not None:
                application = await _application(uow, user_id, job_number)
                target = review_target(kind, application.status)
                if target is not None:
                    application = await uow.applications.set_status(
                        user_id, job_number, target, now
                    )
            reply = await uow.job_replies.review(
                user_id, data.reply_id, job_number, kind, now
            )
            [reply] = _marked([reply], await owner_email(uow, user_id))
            await uow.commit()
        return ReviewedReplyData(
            reply=reply,
            application=None if application is None else application_data(application),
        )

    async def board(self, actor: Actor, query: ReplyQuery) -> ReplyBoard:
        """Черга відповідей для вебу: сторінка за пошуком і лічильники трьох черг (без пошуку).
        Сторінка за межею черги — порожня, не помилка."""
        async with self._unit_of_work() as uow:
            found, total = await uow.job_replies.search(actor.user_id, query)
            counts = await uow.job_replies.counts(actor.user_id)
            email = await owner_email(uow, actor.user_id)
        return ReplyBoard(
            tuple(_marked(found, email)), replace(query.page, total=total), counts
        )

    async def get_reply(self, actor: Actor, reply_id: int) -> ReplyDetailData:
        """Відповідь для читалки: текст підготовлений для людини; подачі власника — з яких
        обирається вакансія. `NotFound` — відповіді нема чи вона чужа."""
        async with self._unit_of_work() as uow:
            found = await uow.job_replies.get(actor.user_id, reply_id)
            if found is None:
                raise NotFound(f"Відповідь {reply_id} не знайдено.")
            applications = await uow.job_replies.applied(actor.user_id)
            [reply] = _marked([found], await owner_email(uow, actor.user_id))
        return ReplyDetailData(
            reply=replace(reply, text=display_text(reply.text)),
            applications=tuple(applications),
        )

    async def preview_review(self, actor: Actor, data: ReviewInput) -> ReviewEffect:
        """Що зробить розбір з подачею, нічого не змінюючи. Ті самі перевірки й правила, що в
        `review_reply`: `InvalidValue` — невідомий тип; `NotFound` — відповіді чи подачі нема."""
        kind = parse_reply_type(data.type)
        user_id, job_number = actor.user_id, data.job_number
        async with self._unit_of_work() as uow:
            if await uow.job_replies.get(user_id, data.reply_id) is None:
                raise NotFound(f"Відповідь {data.reply_id} не знайдено.")
            if job_number is None:
                return review_effect(kind, None, None)
            application = await _application(uow, user_id, job_number)
        return review_effect(kind, job_number, application.status)


async def _application(
    uow: MailUnitOfWork, user_id: UserId, job_number: int
) -> Application:
    """Подача користувача на вакансію; `NotFound` — подачі нема (чи вона чужа)."""
    application = await uow.applications.get(user_id, job_number)
    if application is None:
        raise NotFound(f"Подачі на вакансію {job_number} нема: спершу mark_applied.")
    return application


async def owner_email(uow: MailUnitOfWork, user_id: UserId) -> str:
    """Email із профілю власника — за ним впізнається ручне пересилання."""
    return (await uow.profiles.get(user_id)).contacts.email


def _marked(found: Sequence[Reply], email: str) -> list[Reply]:
    """Відповіді з позначкою ручного пересилання (відправник і тема з блоку)."""
    return [
        replace(
            reply,
            forwarded=manual_forward(
                email, reply.mail.from_address, reply.mail.sender_auth, reply.text
            ),
        )
        for reply in found
    ]
