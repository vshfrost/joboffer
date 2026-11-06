"""Тріаж за правилами без LLM і без ключів API: усі користувачі з вакансіями без тріажу.
Одноразовий запуск — `python -m bootstrap.auto_triage` (сервіс triage у compose; на сервері — таймер).
`--report` лише читає: порівняння з повними аналізами й розподіл вердиктів, нічого не пише;
`--report --detail` додає рядок на вакансію (номер, числа й ознаки «відомо / невідомо» для локації та
формату), підсумок по складниках рубрики та чергу на тріаж (смуги скору за вердиктами, номери
найнижчих analyse й найвищих skip).
У логах лише лічильники й коди помилок, без вмісту вакансій."""

import argparse
import asyncio
import logging
from collections import Counter
from collections.abc import Sequence

from application.triage.auto import AutoTriageUseCases, ComparedJob, PendingJob
from bootstrap.settings import Settings
from domain.triage.scoring import verdict_for
from domain.triage.triage import TriageVerdict
from infrastructure.db.engine import create_engine
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.system import RandomIds, SystemClock

logger = logging.getLogger("joboffer.triage")

# Ширина смуги скору в `--report --detail` і скільки вакансій названо в списках черги.
BAND_WIDTH = 5
PENDING_LISTED = 10


async def run_auto_triage(use_cases: AutoTriageUseCases) -> int:
    """Один прохід; код виходу 0: збій користувача йде в лог (код помилки), решта триває,
    а прогін, що вже йде, цей пропускає."""
    report = await use_cases.run()
    if report.locked:
        logger.info("AUTO_TRIAGE run skipped: інший прогін ще працює")
        return 0
    for user_id, code in report.failures:
        logger.info("AUTO_TRIAGE user=%s error=%s", user_id, code)
    logger.info(
        "AUTO_TRIAGE run done: users=%d triaged=%d failed=%d analyse=%d maybe=%d skip=%d",
        report.users,
        report.triaged,
        len(report.failures),
        report.verdicts[TriageVerdict.ANALYSE],
        report.verdicts[TriageVerdict.MAYBE],
        report.verdicts[TriageVerdict.SKIP],
    )
    return 0


async def run_report(use_cases: AutoTriageUseCases, detail: bool = False) -> int:
    """Звіт без запису в базу; код виходу 0."""
    report = await use_cases.report()
    logger.info(
        "AUTO_TRIAGE report: users=%d compared=%d mean_gap=%+.1f mean_abs_gap=%.1f"
        " agreed=%d analyse=%d maybe=%d skip=%d",
        report.users,
        report.compared,
        report.mean_gap,
        report.mean_abs_gap,
        report.agreed,
        report.verdicts[TriageVerdict.ANALYSE],
        report.verdicts[TriageVerdict.MAYBE],
        report.verdicts[TriageVerdict.SKIP],
    )
    logger.info(
        "AUTO_TRIAGE report pending: total=%d analyse=%d maybe=%d skip=%d",
        report.pending,
        report.pending_verdicts[TriageVerdict.ANALYSE],
        report.pending_verdicts[TriageVerdict.MAYBE],
        report.pending_verdicts[TriageVerdict.SKIP],
    )
    if detail:
        _log_detail(report.jobs)
        _log_pending_detail(report.pending_jobs)
    return 0


# Формати рядків detail-логу зібрані з коротких фрагментів (літерал у коді не довший за 160 символів).
_JOB_DETAIL_FORMAT = " ".join(
    (
        "AUTO_TRIAGE detail job=%d rules=%d analysis=%d gap=%+d rules_verdict=%s",
        "analysis_verdict=%s agreed=%s must=%d role_level=%d format_location=%d",
        "domain=%d nice=%d salary=%d must_req=%d/%d nice_req=%d/%d mismatches=%s",
        "location=%s mode=%s",
    )
)
_SUMMARY_DETAIL_FORMAT = " ".join(
    (
        "AUTO_TRIAGE detail summary: compared=%d mean_gap=%+.1f rules_mean_must=%.1f",
        "rules_mean_role_level=%.1f rules_mean_format_location=%.1f",
        "rules_mean_domain=%.1f rules_mean_nice=%.1f rules_mean_salary=%.1f",
    )
)


def _log_detail(jobs: Sequence[ComparedJob]) -> None:
    """Рядок на порівняну вакансію й підсумок: лише номери й числа, без назв, компаній і тексту.
    Скор аналізу зберігається лише сумою, тому розклад по складниках — тільки в правил."""
    for item in jobs:
        rules, b = item.rules, item.rules.breakdown
        logger.info(
            _JOB_DETAIL_FORMAT,
            item.number,
            rules.score,
            item.analysis_score,
            rules.score - item.analysis_score,
            rules.verdict,
            verdict_for(item.analysis_score),
            "yes" if rules.verdict is verdict_for(item.analysis_score) else "no",
            b.must,
            b.role_level,
            b.format_location,
            b.domain,
            b.nice,
            b.salary,
            b.must_backed,
            b.must_recognised,
            b.nice_backed,
            b.nice_recognised,
            "+".join(m.name.lower() for m in b.mismatches) or "none",
            "known" if item.location_known else "unknown",
            "known" if item.mode_known else "unknown",
        )
    count = len(jobs) or 1
    logger.info(
        _SUMMARY_DETAIL_FORMAT,
        len(jobs),
        sum(i.rules.score - i.analysis_score for i in jobs) / count,
        sum(i.rules.breakdown.must for i in jobs) / count,
        sum(i.rules.breakdown.role_level for i in jobs) / count,
        sum(i.rules.breakdown.format_location for i in jobs) / count,
        sum(i.rules.breakdown.domain for i in jobs) / count,
        sum(i.rules.breakdown.nice for i in jobs) / count,
        sum(i.rules.breakdown.salary for i in jobs) / count,
    )


def _log_pending_detail(pending: Sequence[PendingJob]) -> None:
    """Черга на тріаж: скільки вакансій у кожній п'ятибальній смузі за вердиктами й номери зі скорами
    `PENDING_LISTED` найнижчих analyse та найвищих skip. Лише номери й числа, без вмісту."""
    bands: dict[int, Counter[TriageVerdict]] = {}
    for item in pending:
        bands.setdefault(item.score // BAND_WIDTH * BAND_WIDTH, Counter())[
            item.verdict
        ] += 1
    for start in sorted(bands):
        counts = bands[start]
        logger.info(
            "AUTO_TRIAGE detail pending band_from=%d analyse=%d maybe=%d skip=%d",
            start,
            counts[TriageVerdict.ANALYSE],
            counts[TriageVerdict.MAYBE],
            counts[TriageVerdict.SKIP],
        )
    if not bands:
        logger.info("AUTO_TRIAGE detail pending bands=none")
    analyse = sorted(
        (i for i in pending if i.verdict is TriageVerdict.ANALYSE),
        key=lambda i: (i.score, i.number),
    )
    skip = sorted(
        (i for i in pending if i.verdict is TriageVerdict.SKIP),
        key=lambda i: (-i.score, i.number),
    )
    logger.info(
        "AUTO_TRIAGE detail pending lowest_analyse=%s",
        _listed(analyse[:PENDING_LISTED]),
    )
    logger.info(
        "AUTO_TRIAGE detail pending highest_skip=%s", _listed(skip[:PENDING_LISTED])
    )


def _listed(items: Sequence[PendingJob]) -> str:
    return ",".join(f"{i.number}:{i.score}" for i in items) or "none"


async def _run(settings: Settings, report: bool, detail: bool = False) -> int:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        use_cases = AutoTriageUseCases(
            unit_of_work_factory(engine), SystemClock(), RandomIds()
        )
        if report:
            return await run_report(use_cases, detail)
        return await run_auto_triage(use_cases)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bootstrap.auto_triage",
        description="Тріаж вакансій за правилами без LLM.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="лише звіт: порівняння з аналізами й вердикти, без запису",
    )
    parser.add_argument(
        "--detail", action="store_true", help="з --report: рядок на вакансію"
    )
    args = parser.parse_args(argv)
    if args.detail and not args.report:
        parser.error("--detail працює лише разом з --report")
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    return asyncio.run(_run(Settings(), args.report, args.detail))


if __name__ == "__main__":
    raise SystemExit(main())
