"""Одноразовий імпорт даних v1 → v2: `python -m bootstrap.import_v1 [--apply] [--pdf-dir ТЕКА]`.

Копіює ВСІ дані єдиного користувача з БД v1 (окрема база на тому ж сервері Postgres, з тими ж
обліковими даними) у єдиного користувача v2 однією транзакцією. Без `--apply` — пробний прогін:
друкує, скільки рядків кожної таблиці перенесеться і яких PDF бракує, і нічого не записує.
`--pdf-dir` — тека з PDF оригіналів v1 (`<id документа в v1>.pdf`), відновлена з бекапу;
вони копіюються в `JOBOFFER_DOCUMENTS_DIR` під новим id документа. Вихідний код 0 — виконано,
1 — відмова (нічого не записано).
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.engine import make_url

from application.contracts.v1_import import ImportReport, ImportV1
from application.ports.v1_import import ImportRefused
from application.v1_import.use_cases import ImportV1UseCases
from bootstrap.settings import Settings
from infrastructure.db.engine import create_engine
from infrastructure.db.v1_import.transfer import PostgresV1Import
from infrastructure.pdf.archive import DirectoryPdfArchive
from infrastructure.pdf.files import FileDocuments
from infrastructure.system import RandomIds

DEFAULT_SOURCE_DB = "joboffer_v1"


def render(report: ImportReport, *, has_archive: bool) -> str:
    mode = (
        "Режим: запис (--apply)"
        if report.applied
        else "Режим: пробний прогін, нічого не записано (для запису додай --apply)"
    )
    lines = [mode, "Перенесено рядків:"]
    lines += [f"  {table}: {count}" for table, count in report.counts]
    if not has_archive:
        lines.append("Теку PDF не задано (--pdf-dir): жоден PDF не скопійовано.")
    if report.applied:
        lines.append(f"PDF скопійовано: {report.pdfs_copied}")
    if report.missing_pdfs:
        numbers = ", ".join(str(number) for number in report.missing_pdfs)
        lines.append(f"Немає PDF для документів: {numbers}")
    return "\n".join(lines) + "\n"


async def _import(
    settings: Settings, source_db: str, pdf_dir: Path | None, command: ImportV1
) -> int:
    v2_url = settings.database_url.get_secret_value()
    v1_url = make_url(v2_url).set(database=source_db).render_as_string(False)
    v2 = create_engine(v2_url)
    v1 = create_engine(v1_url)
    try:
        use_cases = ImportV1UseCases(
            PostgresV1Import(v1, v2, RandomIds()),
            None if pdf_dir is None else DirectoryPdfArchive(pdf_dir),
            FileDocuments(settings.documents_dir),
        )
        try:
            report = await use_cases.run(command)
        except ImportRefused as refused:
            sys.stderr.write(f"{refused.message}\n")
            return 1
    finally:
        await v1.dispose()
        await v2.dispose()
    sys.stdout.write(render(report, has_archive=pdf_dir is not None))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bootstrap.import_v1",
        description="Перенести дані єдиного користувача з БД v1 у v2 (без --apply — пробний прогін).",
    )
    parser.add_argument(
        "--apply", action="store_true", help="записати (інакше лише звіт)"
    )
    parser.add_argument(
        "--pdf-dir", type=Path, help="тека з PDF оригіналів v1: <id документа в v1>.pdf"
    )
    parser.add_argument(
        "--source-db",
        default=DEFAULT_SOURCE_DB,
        help=f"імʼя БД v1 на тому ж сервері (типово {DEFAULT_SOURCE_DB})",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _import(Settings(), args.source_db, args.pdf_dir, ImportV1(apply=args.apply))
    )


if __name__ == "__main__":
    raise SystemExit(main())
