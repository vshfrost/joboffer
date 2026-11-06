"""Тріаж за правилами без LLM (cron): сервер сам оцінює вакансії користувачів за профілем,
підтвердженими фактами й текстом (`domain.triage.scoring`).

Користувач — окрема транзакція: збій одного не відкочує вже збережене в інших. Прогін один на базу
(pg advisory lock). Тріаж `agent` (Claude через MCP) cron ніколи не перезаписує. Звіт `report` лише читає."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.triage import AutoTriageUnitOfWork
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.sources.filtering import infer_mode
from domain.triage.ids import TriageId
from domain.triage.scoring import (
    AutoTriage,
    auto_triage,
    context_digest,
    inputs_hash,
    verdict_for,
)
from domain.triage.triage import TriageEntry, TriageVerdict

# Скільки вакансій одного користувача тріажить один прогін; решта — у наступному.
MAX_PER_USER = 200


@dataclass(slots=True)
class AutoTriageReport:
    """Підсумок прогону: лише лічильники й коди помилок, без вмісту вакансій."""

    locked: bool = False
    users: int = 0
    triaged: int = 0
    verdicts: Counter[TriageVerdict] = field(default_factory=Counter)
    # Користувач, чия транзакція відкотилась, і код помилки (ім'я типу винятку).
    failures: list[tuple[UserId, str]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ComparedJob:
    """Одна порівняна вакансія: номер, тріаж правил (з розкладом), скор повного аналізу й
    чи відомі локація та формат (лише булеві ознаки)."""

    number: int
    rules: AutoTriage
    analysis_score: int
    # Чи є в вакансії поле локації й чи визначається формат роботи: лише так, без тексту.
    location_known: bool = False
    mode_known: bool = False


@dataclass(frozen=True, slots=True)
class PendingJob:
    """Вакансія в черзі на тріаж: номер, скор і вердикт правил (без вмісту)."""

    number: int
    score: int
    verdict: TriageVerdict


@dataclass(slots=True)
class ComparisonReport:
    """Тріаж за правилами проти повних аналізів (лише читання, нічого не пишеться)."""

    users: int = 0
    compared: int = 0
    # Середня різниця «скор правил мінус скор аналізу» зі знаком і за модулем.
    mean_gap: float = 0.0
    mean_abs_gap: float = 0.0
    # Скільки вакансій мають однаковий вердикт правил і вердикт за скором аналізу.
    agreed: int = 0
    verdicts: Counter[TriageVerdict] = field(default_factory=Counter)
    # Вакансії, що чекають на тріаж, і вердикти, які правила дали б їм зараз.
    pending: int = 0
    pending_verdicts: Counter[TriageVerdict] = field(default_factory=Counter)
    # Порівняні вакансії по одній (для `--detail`).
    jobs: list[ComparedJob] = field(default_factory=list)
    # Вакансії в черзі по одній (для `--detail`).
    pending_jobs: list[PendingJob] = field(default_factory=list)


class AutoTriageUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], AutoTriageUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids

    async def run(self) -> AutoTriageReport:
        """Тріажить до `MAX_PER_USER` нових і застарілих (`rules`) вакансій кожного користувача з роботою.
        Збій користувача (будь-який виняток) відкочує лише його транзакцію й іде у звіт кодом (ім'я
        типу винятку, без тексту). Прогін, що вже йде в іншому процесі, нічого не робить (`locked`)."""
        report = AutoTriageReport()
        # Лок транзакційний: тримає ця транзакція, яка нічого не пише, до кінця прогону.
        async with self._unit_of_work() as guard:
            if not await guard.triage.lock():
                report.locked = True
                return report
            for user_id in await guard.triage.users_with_work():
                report.users += 1
                try:
                    verdicts = await self._triage_user(user_id)
                except Exception as error:
                    report.failures.append((user_id, type(error).__name__))
                    continue
                report.verdicts.update(verdicts)
                report.triaged += verdicts.total()
        return report

    async def report(self) -> ComparisonReport:
        """Порівнює тріаж правил зі скорами повних аналізів і рахує вердикти для вакансій у черзі
        (до `MAX_PER_USER` на користувача). Лише читає: нічого не зберігає."""
        report = ComparisonReport()
        gaps: list[int] = []
        async with self._unit_of_work() as uow:
            users = await uow.triage.users_with_jobs()
            for user_id in users:
                profile = await uow.profiles.get(user_id)
                facts = await _confirmed_facts(uow, user_id)
                for job, analysis_score in await uow.triage.analysed_scores(user_id):
                    result = auto_triage(job, profile, facts)
                    gaps.append(result.score - analysis_score)
                    report.jobs.append(
                        ComparedJob(
                            job.number,
                            result,
                            analysis_score,
                            location_known=bool(job.location),
                            mode_known=infer_mode([job.location or "", job.text or ""])
                            is not None,
                        )
                    )
                    report.verdicts[result.verdict] += 1
                    if result.verdict is verdict_for(analysis_score):
                        report.agreed += 1
                context = context_digest(profile, facts)
                for job in await uow.triage.auto_candidates(
                    user_id, context, MAX_PER_USER
                ):
                    result = auto_triage(job, profile, facts)
                    report.pending += 1
                    report.pending_verdicts[result.verdict] += 1
                    report.pending_jobs.append(
                        PendingJob(job.number, result.score, result.verdict)
                    )
        report.users = len(users)
        report.compared = len(gaps)
        if gaps:
            report.mean_gap = sum(gaps) / len(gaps)
            report.mean_abs_gap = sum(abs(gap) for gap in gaps) / len(gaps)
        return report

    async def _triage_user(self, user_id: UserId) -> Counter[TriageVerdict]:
        """Одна транзакція користувача: оцінює його кандидатів і зберігає все разом."""
        async with self._unit_of_work() as uow:
            profile = await uow.profiles.get(user_id)
            facts = await _confirmed_facts(uow, user_id)
            context = context_digest(profile, facts)
            jobs = await uow.triage.auto_candidates(user_id, context, MAX_PER_USER)
            verdicts: Counter[TriageVerdict] = Counter()
            items: list[tuple[TriageId, JobId, TriageEntry, str]] = []
            for job in jobs:
                result = auto_triage(job, profile, facts)
                verdicts[result.verdict] += 1
                entry = TriageEntry(
                    job.number, result.score, result.verdict, result.reason
                )
                items.append(
                    (
                        TriageId(self._ids.new()),
                        job.id,
                        entry,
                        inputs_hash(context, job),
                    )
                )
            await uow.triage.save_auto(user_id, items, self._clock.now())
            await uow.commit()
        return verdicts


async def _confirmed_facts(uow: AutoTriageUnitOfWork, user_id: UserId) -> list[str]:
    return [fact.text for fact in await uow.facts.all(user_id) if fact.confirmed]
