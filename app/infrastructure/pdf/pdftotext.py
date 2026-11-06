"""Другий парсер PDF — pdftotext (poppler-utils): текст, який бачить інший ATS."""

import asyncio


class PdftotextMissing(RuntimeError):
    """Утиліти pdftotext нема в системі."""


class PdftotextReader:
    def __init__(self, executable: str = "pdftotext") -> None:
        self._executable = executable

    async def read(self, pdf: bytes) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "-",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise PdftotextMissing(
                f"Утиліти {self._executable} нема (poppler-utils) — "
                "другий парсер PDF недоступний."
            ) from error
        out, err = await process.communicate(pdf)
        if process.returncode != 0:
            raise RuntimeError(
                f"{self._executable} завершився з кодом {process.returncode}: "
                f"{err.decode(errors='replace').strip()}"
            )
        return out.decode()
