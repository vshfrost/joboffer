"""PDF версій у теці на диску: `<корінь>/<id документа>.pdf`. Тека в бекапі сервера.

Ім'я файлу — лише внутрішній UUID документа, ніколи не дані користувача.
"""

import asyncio
from pathlib import Path

from domain.documents.ids import DocumentId


class FileDocuments:
    def __init__(self, root: Path) -> None:
        self._root = root

    async def write(self, document_id: DocumentId, data: bytes) -> None:
        await asyncio.to_thread(self._write, self._path(document_id), data)

    async def read(self, document_id: DocumentId) -> bytes | None:
        return await asyncio.to_thread(self._read, self._path(document_id))

    async def exists(self, document_id: DocumentId) -> bool:
        return await asyncio.to_thread(self._path(document_id).is_file)

    async def delete(self, document_id: DocumentId) -> None:
        await asyncio.to_thread(self._path(document_id).unlink, missing_ok=True)

    def _write(self, path: Path, data: bytes) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        # Атомарно: читач бачить або старий файл, або повний новий, але не половину.
        partial = path.with_suffix(".pdf.partial")
        partial.write_bytes(data)
        partial.replace(path)

    def _read(self, path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def _path(self, document_id: DocumentId) -> Path:
        return self._root / f"{document_id.value}.pdf"
