"""Тека з PDF оригіналів v1, відновлених з бекапу: `<корінь>/<id документа в v1>.pdf`. Лише читання."""

import asyncio
from pathlib import Path


class DirectoryPdfArchive:
    def __init__(self, root: Path) -> None:
        self._root = root

    async def read(self, v1_id: int) -> bytes | None:
        return await asyncio.to_thread(self._read, self._root / f"{v1_id}.pdf")

    def _read(self, path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
