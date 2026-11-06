"""Прогін джерел: усі увімкнені компанії й стрічки всіх користувачів.

Кожну ціль (платформа + слаг компанії чи запит стрічки) адаптер читає один раз, навіть якщо на неї
підписано кількох користувачів; імпорт іде кожному за його профілем. Джерело користувача —
окрема транзакція: вакансії й стан прогону комітяться разом, збій чи крах пізнішого джерела
раніших не відкочує."""

from collections.abc import Callable, Mapping, Sequence

from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.job_sources import JobSource
from application.ports.sources import SourceGone, SourceRunUnitOfWork
from application.sources.imports import SourceImportUseCases
from domain.sources.failure import FailureReason, SourceError
from domain.sources.importing import ImportSummary
from domain.sources.kinds import SourceKind
from domain.sources.posting import Posting
from domain.sources.run import (
    RefreshReport,
    SourceRun,
    Subscription,
    SubscriptionRun,
)
from domain.sources.target import SourceTarget


class SourceRunUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], SourceRunUnitOfWork],
        sources: Mapping[SourceKind, JobSource],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._sources = sources
        self._clock = clock
        self._imports = SourceImportUseCases(unit_of_work, clock, ids)

    async def refresh_sources(self) -> RefreshReport:
        """Читає всі увімкнені джерела й імпортує вакансії; стан кожного джерела користувача —
        один рядок (час, лічильники, код помилки). Збій джерела (`SourceError`, чи нема адаптера
        — `unsupported`) іде в його стан, решта продовжує; так само будь-який інший збій читання
        (`invalid`). Джерело, видалене посеред прогону, пропускається. Прогін, що вже йде в
        іншому процесі, нічого не робить (`locked`). Після прогону всі запити «оновити зараз»,
        що чекали, позначені виконаними."""
        # Лок транзакційний: тримає ця транзакція, яка нічого не пише, до кінця прогону.
        async with self._unit_of_work() as guard:
            if not await guard.source_runs.lock():
                return RefreshReport(locked=True)
            report = RefreshReport()
            for target, subscriptions in _by_target(await guard.source_runs.enabled()):
                await self._refresh_target(target, subscriptions, report)
            await self._mark_requests_handled()
            return report

    async def _mark_requests_handled(self) -> None:
        """Прогін виконав усі запити «оновити зараз», що чекали, — усіх користувачів."""
        async with self._unit_of_work() as uow:
            await uow.source_refresh_requests.mark_handled(self._clock.now())
            await uow.commit()

    async def _refresh_target(
        self,
        target: SourceTarget,
        subscriptions: Sequence[Subscription],
        report: RefreshReport,
    ) -> None:
        postings, error = await self._read(target)
        report.targets += 1
        for subscription in subscriptions:
            try:
                run = await self._import_one(subscription, postings, error)
            except SourceGone:
                # Видалено посеред прогону: його транзакція відкочена, решта йде далі.
                continue
            report.runs.append(SubscriptionRun(subscription, run))

    async def _import_one(
        self,
        subscription: Subscription,
        postings: list[Posting],
        error: FailureReason | None,
    ) -> SourceRun:
        async with self._unit_of_work() as uow:
            summary = ImportSummary()
            if error is None:
                summary = await self._imports.import_in(
                    uow,
                    subscription.user_id,
                    subscription.kind,
                    postings,
                    subscription.name,
                )
            run = SourceRun(self._clock.now(), summary, error)
            await uow.source_runs.save(subscription, run)
            await uow.commit()
        return run

    async def _read(
        self, target: SourceTarget
    ) -> tuple[list[Posting], FailureReason | None]:
        source = self._sources.get(target.kind)
        if source is None:
            return [], FailureReason.UNSUPPORTED
        try:
            return await source.fetch(target), None
        except SourceError as exc:
            return [], exc.reason
        except Exception:
            # Збій адаптера не обриває прогін. Текст винятку може містити шматок недовіреної
            # відповіді джерела, тому він нікуди не йде: у стан і аудит — лише код `invalid`.
            return [], FailureReason.INVALID


def _by_target(
    subscriptions: Sequence[Subscription],
) -> list[tuple[SourceTarget, list[Subscription]]]:
    """Підписки за ціллю, у порядку першої появи. Назва компанії — своя в кожного користувача,
    тож у спільну ціль вона не входить."""
    groups: dict[SourceTarget, list[Subscription]] = {}
    for subscription in subscriptions:
        target = SourceTarget(subscription.kind, subscription.ref)
        groups.setdefault(target, []).append(subscription)
    return list(groups.items())
