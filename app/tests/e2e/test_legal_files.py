"""Файли умов і політики: версія зі шапки, зіпсований файл падає на старті з назвою файлу."""

from pathlib import Path

import pytest

from application.contracts.legal import LegalDoc
from application.ports.legal import LegalDocumentsUnavailableError
from infrastructure.legal.files import FileLegalDocuments

GOOD = "---\nверсія: 2026-01-02.3\n---\nТекст\nдокумента\n"


def write(root: Path, doc: LegalDoc, content: bytes) -> None:
    (root / "legal").mkdir(exist_ok=True)
    (root / "legal" / f"{doc.value}.md").write_bytes(content)


def write_all(root: Path, content: bytes = GOOD.encode()) -> None:
    for doc in LegalDoc:
        write(root, doc, content)


def test_version_and_text_come_from_the_file(tmp_path: Path) -> None:
    write_all(tmp_path)
    document = FileLegalDocuments.load(tmp_path).get(LegalDoc.TERMS)
    assert (document.version, document.text) == ("2026-01-02.3", "Текст\nдокумента")


def test_windows_line_endings_are_accepted(tmp_path: Path) -> None:
    write_all(tmp_path, GOOD.replace("\n", "\r\n").encode())
    assert FileLegalDocuments.load(tmp_path).get(LegalDoc.PRIVACY).text == (
        "Текст\nдокумента"
    )


def test_missing_file_fails_naming_the_file(tmp_path: Path) -> None:
    write(tmp_path, LegalDoc.TERMS, GOOD.encode())
    with pytest.raises(LegalDocumentsUnavailableError, match=r"privacy\.md"):
        FileLegalDocuments.load(tmp_path)


def test_non_utf8_file_fails(tmp_path: Path) -> None:
    write_all(tmp_path, b"\xff\xfe")
    with pytest.raises(LegalDocumentsUnavailableError, match=r"terms\.md"):
        FileLegalDocuments.load(tmp_path)


@pytest.mark.parametrize("content", ["Текст без шапки", "---\nверсія: 1\n---\nТ"])
def test_file_without_valid_version_header_fails(tmp_path: Path, content: str) -> None:
    write_all(tmp_path, content.encode())
    with pytest.raises(LegalDocumentsUnavailableError, match="без версії"):
        FileLegalDocuments.load(tmp_path)
