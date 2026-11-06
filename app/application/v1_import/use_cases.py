"""Імпорт даних v1 → v2: рядки однією транзакцією, PDF до її фіксації.

PDF копіюються до `commit()`: якщо файл не вдалося записати чи фіксація впала, усе відкочується,
а вже записані файли прибираються — повторний запуск стартує з чистого стану.
"""

from application.contracts.v1_import import ImportReport, ImportV1
from application.ports.v1_import import PdfSink, V1Import, V1PdfArchive
from domain.documents.ids import DocumentId


class ImportV1UseCases:
    def __init__(
        self, source: V1Import, archive: V1PdfArchive | None, files: PdfSink
    ) -> None:
        self._source = source
        self._archive = archive
        self._files = files

    async def run(self, command: ImportV1) -> ImportReport:
        """Пробний прогін проходить увесь перенос у транзакції, яку відкочує: лічильники вже
        враховують обмеження v2, але нічого не лишається. PDF читаються в обох режимах (щоб
        звіт показав, яких бракує), а пишуться лише з `apply`."""
        written: list[DocumentId] = []
        missing: list[int] = []
        async with self._source.begin() as transfer:
            copied = await transfer.copy()
            try:
                for document in copied.documents:
                    data = (
                        None
                        if self._archive is None
                        else await self._archive.read(document.v1_id)
                    )
                    if data is None:
                        missing.append(document.v1_id)
                    elif command.apply:
                        await self._files.write(document.document_id, data)
                        written.append(document.document_id)
                if command.apply:
                    await transfer.commit()
            except BaseException:
                for document_id in written:
                    await self._files.delete(document_id)
                raise
        return ImportReport(
            applied=command.apply,
            counts=copied.counts,
            missing_pdfs=tuple(missing),
            pdfs_copied=len(written),
        )
