"""Адаптер порту `Prompts`: промпти з файлів `<корінь>/<область>/<імʼя>.md`."""

from pathlib import Path
from typing import Self

from application.ports.prompts import PromptKey, PromptsUnavailableError


class FilePrompts:
    def __init__(self, texts: dict[PromptKey, str]) -> None:
        self._texts = texts

    @classmethod
    def load(cls, root: Path) -> Self:
        """Читає всі ключі одразу: відсутній чи зіпсований файл падає на старті, не під час запиту."""
        return cls({key: _read(root / f"{key.value}.md") for key in PromptKey})

    def get(self, key: PromptKey) -> str:
        return self._texts[key]


def _read(path: Path) -> str:
    try:
        # Байти й явне декодування: переведення рядків у файлі не нормалізуються.
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PromptsUnavailableError(f"Промпт недоступний: {path}: {exc}") from exc
