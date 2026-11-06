"""PdftotextReader: другий парсер PDF — утиліта pdftotext (poppler-utils) у окремому процесі."""

from io import BytesIO

import pytest
from anyio.from_thread import BlockingPortal
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from infrastructure.pdf.pdftotext import PdftotextMissing, PdftotextReader


def pdf_saying(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(200, 100)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = StreamObject()
    stream.set_data(f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    data = BytesIO()
    writer.write(data)
    return data.getvalue()


def test_the_text_of_a_pdf_is_read_by_pdftotext(portal: BlockingPortal) -> None:
    text = portal.call(PdftotextReader().read, pdf_saying("Built APIs with Kafka"))

    assert text.split() == ["Built", "APIs", "with", "Kafka"]


def test_a_missing_utility_is_an_explicit_error_not_silent_success(
    portal: BlockingPortal,
) -> None:
    reader = PdftotextReader("pdftotext-that-is-not-installed")

    with pytest.raises(PdftotextMissing, match="pdftotext-that-is-not-installed"):
        portal.call(reader.read, pdf_saying("Kafka"))
