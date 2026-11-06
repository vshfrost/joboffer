"""FileDocuments: PDF версій у теці на диску, ключ — id документа, запис атомарний."""

from pathlib import Path
from uuid import UUID

import pytest
from anyio.from_thread import BlockingPortal

from domain.documents.ids import DocumentId
from infrastructure.pdf.files import FileDocuments

FIRST = DocumentId(UUID(int=1))
SECOND = DocumentId(UUID(int=2))


def test_a_missing_file_reads_as_none(portal: BlockingPortal, tmp_path: Path) -> None:
    files = FileDocuments(tmp_path / "documents")
    assert portal.call(files.read, FIRST) is None


def test_a_written_file_reads_back_byte_for_byte(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    files = FileDocuments(tmp_path / "documents")
    data = b"%PDF-1.7\n\x00\xff binary \r\n"

    portal.call(files.write, FIRST, data)

    assert portal.call(files.read, FIRST) == data


def test_the_folder_is_created_on_the_first_write(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    root = tmp_path / "deep" / "documents"

    portal.call(FileDocuments(root).write, FIRST, b"%PDF-1")

    assert [p.name for p in root.iterdir()] == [f"{FIRST}.pdf"]


def test_a_rewrite_replaces_the_file_whole_and_leaves_no_partial(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    files = FileDocuments(tmp_path / "documents")

    portal.call(files.write, FIRST, b"%PDF-1")
    portal.call(files.write, FIRST, b"%PDF-2")

    assert portal.call(files.read, FIRST) == b"%PDF-2"
    assert sorted(p.name for p in (tmp_path / "documents").iterdir()) == [
        f"{FIRST}.pdf"
    ]


def test_versions_live_in_separate_files(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    files = FileDocuments(tmp_path / "documents")

    portal.call(files.write, FIRST, b"first")
    portal.call(files.write, SECOND, b"second")

    assert portal.call(files.read, FIRST) == b"first"
    assert portal.call(files.read, SECOND) == b"second"


def test_the_file_name_comes_only_from_the_internal_id(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    root = tmp_path / "documents"
    portal.call(FileDocuments(root).write, SECOND, b"x")

    assert (root / f"{SECOND.value}.pdf").read_bytes() == b"x"


@pytest.mark.parametrize("failure", ["root_is_a_file"])
def test_a_write_that_cannot_happen_is_an_error_not_silence(
    portal: BlockingPortal, tmp_path: Path, failure: str
) -> None:
    blocked = tmp_path / "documents"
    blocked.write_bytes(b"not a folder")

    with pytest.raises(OSError):  # noqa: PT011
        portal.call(FileDocuments(blocked).write, FIRST, b"x")


def test_a_file_exists_only_after_it_is_written(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    files = FileDocuments(tmp_path / "documents")

    assert portal.call(files.exists, FIRST) is False
    portal.call(files.write, FIRST, b"%PDF-1")

    assert portal.call(files.exists, FIRST) is True
    assert portal.call(files.exists, SECOND) is False


def test_a_deleted_file_is_gone_and_the_others_stay(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    files = FileDocuments(tmp_path / "documents")
    portal.call(files.write, FIRST, b"first")
    portal.call(files.write, SECOND, b"second")

    portal.call(files.delete, FIRST)

    assert portal.call(files.exists, FIRST) is False
    assert portal.call(files.read, FIRST) is None
    assert portal.call(files.read, SECOND) == b"second"


def test_deleting_a_file_that_is_not_there_is_not_an_error(
    portal: BlockingPortal, tmp_path: Path
) -> None:
    files = FileDocuments(tmp_path / "documents")

    portal.call(files.delete, FIRST)

    assert portal.call(files.exists, FIRST) is False
