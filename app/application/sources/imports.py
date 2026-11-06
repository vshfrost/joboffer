"""Імпорт вакансій із джерела: фільтр за профілем користувача, дедуп, нова вакансія чи дописаний текст.

Мережі тут нема: вакансії приносить адаптер джерела (вони вже очищені `sanitize`)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.sources import SourceImportUnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.profile.profile import Profile
from domain.sources.dedup import DEDUP_WINDOW, RecentJob, find_same_job
from domain.sources.filtering import skip_reason
from domain.sources.importing import ImportSummary, Outcome
from domain.sources.kinds import SourceKind, source_label
from domain.sources.posting import Posting


class SourceImportUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], SourceImportUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids

    async def import_postings(
        self,
        user_id: UserId,
        source: SourceKind,
        postings: Sequence[Posting],
        company: str = "",
    ) -> ImportSummary:
        """Вакансії одного джерела → вакансії користувача за його профілем, в одній транзакції.
        `company` — назва компанії цілі для вакансій, що власної компанії не мають.

        Не за профілем — відкидається. Той самий URL чи текст у користувача, чи та сама пара
        «компанія + посада» за `DEDUP_WINDOW` (ATS, DOU, Djinni і LinkedIn публікують одне під
        різними URL; сховану вакансію теж враховано) — дубль; якщо така вакансія з алерту LinkedIn
        ще без тексту, їй дописується текст (назва, компанія й URL LinkedIn лишаються)."""
        async with self._unit_of_work() as uow:
            summary = await self.import_in(uow, user_id, source, postings, company)
            await uow.commit()
        return summary

    async def import_in(
        self,
        uow: SourceImportUnitOfWork,
        user_id: UserId,
        source: SourceKind,
        postings: Sequence[Posting],
        company: str = "",
    ) -> ImportSummary:
        """Той самий імпорт у транзакції викликача: комітить вона (прогін джерел зберігає разом
        з вакансіями стан джерела)."""
        now = self._clock.now()
        await uow.jobs.lock_additions(user_id)
        batch = _Batch(
            uow=uow,
            user_id=user_id,
            source=source_label(source),
            company=company,
            profile=await uow.profiles.get(user_id),
            recent=await uow.jobs.recent(user_id, now - DEDUP_WINDOW),
        )
        outcomes = [await self._import_one(batch, posting, now) for posting in postings]
        return ImportSummary.of(outcomes)

    async def _import_one(
        self, batch: _Batch, posting: Posting, now: datetime
    ) -> Outcome:
        if skip_reason(posting, batch.profile) is not None:
            return Outcome.FILTERED
        owner = posting.company or batch.company
        job = NewJob(
            text=posting.text,
            url=posting.url,
            title=posting.title,
            company=owner or None,
            location=posting.location,
            source=batch.source,
        )
        jobs = batch.uow.jobs
        if await jobs.find_duplicate(batch.user_id, job) is not None:
            return Outcome.DUPLICATE
        same = find_same_job(batch.recent, owner, posting.title)
        if same is None:
            number = await jobs.add(batch.user_id, JobId(self._ids.new()), job, now)
            batch.recent.append(RecentJob(number, owner or None, posting.title, False))
            return Outcome.IMPORTED
        if same.needs_text:
            await jobs.complete_text(batch.user_id, same.number, posting.text)
            return Outcome.COMPLETED
        return Outcome.DUPLICATE


@dataclass(slots=True)
class _Batch:
    """Що знають усі вакансії одного імпорту; `recent` росте з кожною доданою вакансією."""

    uow: SourceImportUnitOfWork
    user_id: UserId
    source: str
    company: str
    profile: Profile
    recent: list[RecentJob]
