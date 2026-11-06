"""Адаптер порту `LegalDocuments`: `<корінь>/legal/<doc>.md` з рядком `версія: …` у шапці між `---`."""

import re
from pathlib import Path
from typing import Self

from application.contracts.legal import LegalDoc, LegalDocument
from application.ports.legal import LegalDocumentsUnavailableError

_FILE = re.compile(r"---\nверсія: (\d{4}-\d{2}-\d{2}\.\d+)\n---\n(.+)", re.DOTALL)


class FileLegalDocuments:
    def __init__(self, documents: dict[LegalDoc, LegalDocument]) -> None:
        self._documents = documents

    @classmethod
    def load(cls, root: Path) -> Self:
        """Читає обидва документи одразу: відсутній чи зіпсований файл падає на старті."""
        return cls(
            {doc: _read(doc, root / "legal" / f"{doc.value}.md") for doc in LegalDoc}
        )

    def get(self, doc: LegalDoc) -> LegalDocument:
        return self._documents[doc]


def _read(doc: LegalDoc, path: Path) -> LegalDocument:
    try:
        raw = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LegalDocumentsUnavailableError(
            f"Документ недоступний: {path}: {exc}"
        ) from exc
    found = _FILE.fullmatch(raw.replace("\r\n", "\n"))
    if found is None:
        raise LegalDocumentsUnavailableError(f"Документ без версії у шапці: {path}")
    return LegalDocument(doc=doc, version=found.group(1), text=found.group(2).strip())
