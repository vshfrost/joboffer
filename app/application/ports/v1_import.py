"""Порти імпорту v1 → v2: перенос рядків між двома базами і копіювання PDF.

Перенос іде в одній транзакції бази v2: `copy()` пише рядки, `commit()` її фіксує; вихід із
`begin()` без `commit()` усе відкочує (так працює і пробний прогін).
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from domain.documents.ids import DocumentId
from domain.shared.errors import Conflict


class ImportRefused(Conflict):
    """Імпорт не стартував: стан баз не відповідає очікуваному (нічого не записано)."""

    code = "import_refused"


@dataclass(frozen=True, slots=True)
class ImportedDocument:
    """Документ v1, якому в v2 дали новий `document_id`; номер у v2 = `v1_id`."""

    v1_id: int
    document_id: DocumentId


@dataclass(frozen=True, slots=True)
class Copied:
    counts: tuple[tuple[str, int], ...]
    documents: tuple[ImportedDocument, ...]


class V1Transfer(Protocol):
    async def copy(self) -> Copied:
        """Перевіряє обидві бази й переносить дані. `ImportRefused` — стан не той."""
        ...

    async def commit(self) -> None: ...


class V1Import(Protocol):
    def begin(self) -> AbstractAsyncContextManager[V1Transfer]:
        """Відкриває читання v1 і транзакцію запису у v2."""
        ...


class V1PdfArchive(Protocol):
    """PDF оригіналів v1, відновлені з бекапу: ключ — id документа в v1."""

    async def read(self, v1_id: int) -> bytes | None:
        """None — файлу нема."""
        ...


class PdfSink(Protocol):
    """Тека PDF документів v2."""

    async def write(self, document_id: DocumentId, data: bytes) -> None: ...

    async def delete(self, document_id: DocumentId) -> None: ...
