"""Адаптер порту `Templates`: шаблони з файлів `<корінь>/<область>/<імʼя>.html`
(листи, область `mail`, — звичайний текст: `.txt`)."""

from pathlib import Path
from typing import Self

from application.ports.templates import TemplateKey, TemplatesUnavailableError


class FileTemplates:
    def __init__(self, texts: dict[TemplateKey, str]) -> None:
        self._texts = texts

    @classmethod
    def load(cls, root: Path) -> Self:
        """Читає всі ключі одразу: відсутній чи зіпсований файл падає на старті, не під час запиту."""
        return cls(
            {key: _read(root / f"{key.value}{_suffix(key)}") for key in TemplateKey}
        )

    def get(self, key: TemplateKey) -> str:
        return self._texts[key]


def _suffix(key: TemplateKey) -> str:
    return ".txt" if key.value.startswith("mail/") else ".html"


def _read(path: Path) -> str:
    try:
        # Байти й явне декодування: переведення рядків у файлі не нормалізуються.
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TemplatesUnavailableError(f"Шаблон недоступний: {path}: {exc}") from exc
