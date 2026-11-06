"""Прогін джерел вакансій: усі увімкнені компанії й стрічки всіх користувачів. Одноразовий запуск —
`python -m bootstrap.refresh_sources` (сервіс sources у compose; на сервері — таймер, B12).
Аудит — рядки SOURCES_AUDIT без вмісту вакансій."""

import asyncio
import logging

from application.sources.refresh import SourceRunUseCases
from bootstrap.settings import Settings
from domain.sources.kinds import source_label
from infrastructure.db.engine import create_engine
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.sources import build_sources
from infrastructure.sources.http import Fetcher, new_client
from infrastructure.system import RandomIds, SystemClock

logger = logging.getLogger("joboffer.sources")


async def run_refresh(use_cases: SourceRunUseCases) -> int:
    """Один прохід прогону; код виходу процесу — 0: збій окремого джерела записано в його стан
    (і в аудит), а прогін, що вже йде, цей пропускає."""
    report = await use_cases.refresh_sources()
    if report.locked:
        logger.info("SOURCES_AUDIT run skipped: інший прогін ще працює")
        return 0
    for item in report.runs:
        subscription, run, summary = item.subscription, item.run, item.run.summary
        logger.info(
            "SOURCES_AUDIT source=%s ref=%s user=%s found=%d imported=%d filtered=%d"
            " duplicate=%d completed=%d error=%s",
            source_label(subscription.kind),
            subscription.ref,
            subscription.user_id,
            summary.found,
            summary.imported,
            summary.filtered,
            summary.duplicate,
            summary.completed,
            run.error.value if run.error else "-",
        )
    failed = sum(1 for item in report.runs if item.run.error is not None)
    logger.info(
        "SOURCES_AUDIT run done: targets=%d sources=%d failed=%d",
        report.targets,
        len(report.runs),
        failed,
    )
    return 0


async def _run(settings: Settings) -> int:
    engine = create_engine(settings.database_url.get_secret_value())
    client = new_client()
    try:
        use_cases = SourceRunUseCases(
            unit_of_work_factory(engine),
            build_sources(Fetcher(client)),
            SystemClock(),
            RandomIds(),
        )
        return await run_refresh(use_cases)
    finally:
        await client.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    code = asyncio.run(_run(Settings()))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
